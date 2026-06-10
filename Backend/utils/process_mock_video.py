import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst
from supervision import Detections
from ultralytics import YOLO
from category_classifier import CategoryClassifier
from peewee import *
import uuid
from mock_gstreamer_app import MockVideoGStreamerApp, get_caps_from_pad, get_numpy_from_buffer
import sys
from multiprocessing import Queue, Process
import numpy as np
from get_frame_index_from_buffer import load_get_frame_index_from_buffer
import cv2

db = SqliteDatabase('mock_videos.db')


class BaseModel(Model):
    class Meta:
        database = db


class BBox(BaseModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4())
    x1 = IntegerField()
    y1 = IntegerField()
    x2 = IntegerField()
    y2 = IntegerField()
    label = TextField()
    confidence = FloatField()
    frame_index = IntegerField()
    video_name = TextField()

all_tables = [
    BBox
]

def init_db():
    current_tables = db.get_tables()
    tables_to_create = list(filter(lambda e: str(e) not in current_tables, all_tables))
    db.create_tables(tables_to_create)


category_classes = [
    'can',
    'plastic',
    'drinkbox',
    'gabletop',
    'pouch'
]

if __name__ == '__main__':
    init_db()

    video_dir = sys.argv[1]
    yolo_model_path = sys.argv[2]
    category_model_path = sys.argv[3]

    yolo_model = YOLO(yolo_model_path)
    category_model = CategoryClassifier(category_model_path)

    def on_state_changed(status, error=None, debug=None):
        print(f'state changed: {status}')

    def on_stopped():
        print('on stopped called')
    
    gstreamer_app = MockVideoGStreamerApp(
        on_state_changed=on_state_changed,
        on_stopped=on_stopped,
        first_file_name=None,
        user_data=None,
        video_dir=video_dir,
        fps=30,
        loop=False,
        print_progress=True
    )

    def processing_queue(queue: Queue):
        while True:
            frame, index, video_name = queue.get()
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            yolo_results = yolo_model.predict(frame, agnostic_ms=True, verbose=False)[0]
            yolo_detections = Detections.from_ultralytics(yolo_results)
            def crop_bbox_from_frame(xyxy: np.ndarray):
                x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                bbox = bgr_frame[y1:y2, x1:x2]
                return bbox
            cropped_bboxes = list(map(crop_bbox_from_frame, yolo_detections.xyxy))
            categories = category_model.run_inference(cropped_bboxes)

            bboxes_to_save: list[BBox] = []
            for xyxy, confidence, category in zip(yolo_detections.xyxy, yolo_detections.confidence, categories):
                bboxes_to_save.append(BBox(
                    x1=xyxy[0],
                    y1=xyxy[1],
                    x2=xyxy[2],
                    y2=xyxy[3],
                    label=category_classes[category],
                    confidence=confidence,
                    frame_index=index,
                    video_name=video_name
                ))

            BBox.bulk_create(bboxes_to_save)
            print(f'Processed frame {index} of video {video_name}')


    queue = Queue()

    processing_process = Process(target=processing_queue, args=[queue])
    processing_process.start()

    get_frame_index_from_buffer = load_get_frame_index_from_buffer()

    def dummy_app_callback(pad, info, user_data):
        buffer = info.get_buffer()
        # Check if the buffer is valid
        if buffer is None:
            return Gst.PadProbeReturn.OK
        
        frame = get_numpy_from_buffer(buffer, format, width, height)

        
        frame_index = get_frame_index_from_buffer(buffer)

        format, width, height = get_caps_from_pad(pad)
        
        queue.put((frame, frame_index, gstreamer_app.video_files[gstreamer_app.current_video_index]))
        
        return Gst.PadProbeReturn.OK

    gstreamer_app.app_callback = dummy_app_callback
    gstreamer_app.collect_raw_frames = False
    gstreamer_app.create_pipeline()
    gstreamer_app.run()
    GLib.MainLoop().run()