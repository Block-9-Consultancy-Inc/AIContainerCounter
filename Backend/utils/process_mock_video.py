import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst
from supervision import Detections
import torch
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
import uuid
import os
from time import sleep

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

def processing_queue(queue: Queue, yolo_model_path: str, category_model_path: str, camera_calibration_params_path: str):
    yolo_model = YOLO(yolo_model_path)
    category_model = CategoryClassifier(category_model_path)
    with np.load(camera_calibration_params_path) as data:
        camera_mtx = data.get('camera_matrix')
        dist_coeffs = data.get('dist_coeffs')

    new_camera_mtx, roi = cv2.getOptimalNewCameraMatrix(camera_mtx, dist_coeffs, (1920, 1080), 0)
    map1, map2 = cv2.initUndistortRectifyMap(camera_mtx, dist_coeffs, None, new_camera_mtx, (1920, 1080), cv2.CV_16SC2)
    
    while True:
        frame, index, video_name = queue.get()
        rgb_frame = cv2.remap(frame, map1, None, None)
        bgr_frame = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
        yolo_results = yolo_model.predict(bgr_frame, agnostic_nms=True, verbose=False)[0]
        yolo_detections = Detections.from_ultralytics(yolo_results)
        def crop_bbox_from_frame(xyxy: np.ndarray):
            x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
            bbox = rgb_frame[y1:y2, x1:x2]
            return bbox
        cropped_bboxes = list(map(crop_bbox_from_frame, yolo_detections.xyxy))
        categories = category_model.run_inference(cropped_bboxes) if len(cropped_bboxes) > 0 else []

        bboxes_to_save: list[BBox] = []
        for xyxy, confidence, category in zip(yolo_detections.xyxy, yolo_detections.confidence, categories):
            bboxes_to_save.append(BBox(
                id=str(uuid.uuid4()),
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
        # print(f'Processed frame {index} of video {video_name}')

if __name__ == '__main__':
    torch.multiprocessing.set_start_method('spawn')# good solution !!!!
    init_db()

    video_dir = sys.argv[1]
    yolo_model_path = sys.argv[2]
    category_model_path = sys.argv[3]

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

    camera_calibration_params_path = "./resources/camera_calibration_data_1.npz"


    queue = Queue(2000)

    processing_process = Process(target=processing_queue, args=[queue, yolo_model_path, category_model_path, camera_calibration_params_path])
    processing_process.start()

    get_frame_index_from_buffer = load_get_frame_index_from_buffer()

    videos = os.listdir(video_dir)

    def dummy_app_callback(pad, info, user_data):
        buffer = info.get_buffer()
        # Check if the buffer is valid
        if buffer is None:
            return Gst.PadProbeReturn.OK

        format, width, height = get_caps_from_pad(pad)
        
        frame = get_numpy_from_buffer(buffer, format, width, height)

        
        frame_index = get_frame_index_from_buffer(buffer)

        
        queue.put((frame, frame_index, videos[gstreamer_app.current_video_index]))

        return Gst.PadProbeReturn.OK

    gstreamer_app.app_callback = dummy_app_callback
    gstreamer_app.collect_raw_frames = False
    gstreamer_app.create_pipeline()
    gstreamer_app.run()
    while True:
        sleep(2)
        if gstreamer_app.pipeline.get_state(Gst.CLOCK_TIME_NONE)[1] == Gst.State.PLAYING:
            if queue.full():
                print(f'PAUSING PIPELINE: QUEUE FULL')
                gstreamer_app.pipeline.set_state(Gst.State.PAUSED)
            else:
                print(f'PIPELINE PLAYING QUEUE SIZE: {queue.qsize()}')
        elif gstreamer_app.pipeline.get_state(Gst.CLOCK_TIME_NONE)[1] == Gst.State.PAUSED:
            if not queue.full() and 2000 - queue.qsize() > 1000:
                print(f'QUEUE HAS SPACE: REPLAYING')
                gstreamer_app.pipeline.set_state(Gst.State.PLAYING)
            else:
                print(f'QUEUE DOES NOT HAVE SPACE: QUEUE SIZE: {queue.qsize()}')
        else:
            print(f'PIPELINE NOT PLAYING OR PAUSED, STATE: {gstreamer_app.pipeline.get_state(Gst.CLOCK_TIME_NONE)}')


