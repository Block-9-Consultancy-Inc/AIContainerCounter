from flask import Flask
from os import environ
import socketio
import base64
from threading import Thread
from ultralytics import YOLO, solutions
from turbojpeg import TurboJPEG, TJFLAG_FASTUPSAMPLE, TJFLAG_FASTDCT
from flask_cors import CORS
import torch
from linuxpy.video.device import Device, BufferType
from time import perf_counter_ns, perf_counter
from dotenv import load_dotenv
import sys
import cv2
import numpy as np
import json
from random import random
from supervision import TraceAnnotator, BoundingBoxAnnotator, LabelAnnotator, Detections, ByteTrack, LineZoneAnnotator, LineZone, Point, Position
from utils.category_classifier import CategoryClassifier
import traceback

category_classes = [
    'can',
    'plastic',
    'drinkbox',
    'gabletop',
    'pouch'
]

class Counter:
    def __init__(self, names: list[str], width: int, height: int):
        self.width = width
        self.height = height
        self.names = names
        self.byte_tracker = ByteTrack()
        self.line_zone = LineZone(start=Point(self.width / 2, 0), end=Point(self.width / 2, self.height), triggering_anchors=[Position.CENTER])
        self.line_zone_annotator = LineZoneAnnotator(text_scale=1, thickness=2, text_thickness=2)
        self.box_annotator = BoundingBoxAnnotator(thickness=2)
        self.trace_annotator = TraceAnnotator(thickness=2)
        self.label_annotator = LabelAnnotator(text_thickness=2, text_scale=1)
        self.category_classifier = CategoryClassifier('resnet_v1_18_unscaled.pth')
        self.tracker_id_to_category = {}
        self.category_counts = {
            'can': 0,
            'plastic': 0,
            'drinkbox': 0,
            'gabletop': 0,
            'pouch': 0
        }

    def trigger(self, decoded_frame: np.ndarray, detections: Detections):
        detections = self.byte_tracker.update_with_detections(detections)

        annotated_frame = self.trace_annotator.annotate(
            scene=decoded_frame.copy(),
            detections=detections)
        annotated_frame = self.box_annotator.annotate(
            scene=annotated_frame,
            detections=detections)
        

        center_crossed_in, center_crossed_out = self.line_zone.trigger(detections)
        annotated_frame = self.line_zone_annotator.annotate(annotated_frame, line_counter=self.line_zone)

        center_crossed_in_coords = np.argwhere(center_crossed_in == True)
        if center_crossed_in_coords.shape[0] == 0:
            labels = [
                f"#{tracker_id} {self.names[class_id] if self.tracker_id_to_category.get(tracker_id) is None else category_classes[self.tracker_id_to_category.get(tracker_id)]} {confidence:0.2f}"
                for confidence, class_id, tracker_id
                in zip(detections.confidence, detections.class_id, detections.tracker_id)
            ]

            annotated_frame = self.label_annotator.annotate(
                scene=annotated_frame,
                detections=detections,
                labels=labels)
            return annotated_frame, self.line_zone.in_count, self.line_zone.out_count

        try:
            squeeze_axis = 0
            if center_crossed_in_coords.shape[0] > 1:
                squeeze_axis = 1

            xyxy = detections.xyxy[center_crossed_in]
            confidence = np.squeeze(detections.confidence[center_crossed_in_coords], axis=squeeze_axis)
            class_id = np.squeeze(detections.class_id[center_crossed_in_coords].astype(int), axis=squeeze_axis)
            tracker_id = np.squeeze(detections.tracker_id[center_crossed_in_coords].astype(int), axis=squeeze_axis)
            center_crossed_in_detections = Detections(
                    xyxy=xyxy, 
                    confidence=confidence, 
                    class_id=class_id,
                    tracker_id=tracker_id
                )
            
            def crop_bbox_from_frame(xyxy: np.ndarray):
                x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                bbox = decoded_frame[y1:y2, x1:x2]
                return bbox
            center_crossed_in_bboxes = list(map(crop_bbox_from_frame, center_crossed_in_detections.xyxy))
            categories = self.category_classifier.run_inference(center_crossed_in_bboxes)
            for index, category in enumerate(categories):
                self.tracker_id_to_category[center_crossed_in_detections.tracker_id[index]] = category
            unique, category_counts = np.unique(categories, return_counts=True)
            category_counts = dict(zip(unique, category_counts))
            for class_index, count in category_counts.items():
                self.category_counts[category_classes[class_index]] += int(count)
            
            labels = [
                f"#{tracker_id} {self.names[class_id] if self.tracker_id_to_category.get(tracker_id) is None else category_classes[self.tracker_id_to_category.get(tracker_id)]} {confidence:0.2f}"
                for confidence, class_id, tracker_id
                in zip(detections.confidence, detections.class_id, detections.tracker_id)
            ]

            annotated_frame = self.label_annotator.annotate(
                scene=annotated_frame,
                detections=detections,
                labels=labels)

            return annotated_frame, self.line_zone.in_count, self.line_zone.out_count
        except Exception as e:
            print(f'got error in counter trigger: {e}')
            error_traceback = traceback.format_exc()
            print(error_traceback)
    
    def reset_counter(self):
        self.byte_tracker = ByteTrack()
        self.line_zone = LineZone(start=Point(self.width / 2, 0), end=Point(self.width / 2, self.height), triggering_anchors=[Position.CENTER])
        self.category_counts = {
            'can': 0,
            'plastic': 0,
            'drinkbox': 0,
            'gabletop': 0,
            'pouch': 0
        }

class CounterApp:
    def __init__(self,
            load_params_from_dotenv = True,
            dotenv_path = './.env',
            force_transmit_video = False,
            height = 1080,
            width = 1920,
            camera_id = 0,
            camera_fps = 60,
            counting_region_width_percentage = 0.4,
            model_path = 'counting-machine-1-category-yolo11.pt',
            model_imgsz = 1440,
            frame_encode_quality = 85,
            render_debug_count = True,
            print_debug_performance_metrics = True,
            turbo_jpeg_library_path: str = None,
            camera_calibration_params_path: str = None,
            mocked_counts_path: str = None
        ) -> None:

        self.force_transmit_video = force_transmit_video

        if not load_params_from_dotenv:
            self.height = height
            self.width = width
            self.camera_id = camera_id
            self.camera_fps = camera_fps
            self.counting_region_width_percentage = counting_region_width_percentage
            self.model_path = model_path
            self.model_imgsz = model_imgsz
            self.frame_encode_quality = frame_encode_quality
            self.render_debug_count = render_debug_count
            self.print_debug_performance_metrics = print_debug_performance_metrics
            self.turbo_jpeg_library_path = turbo_jpeg_library_path
            self.camera_calibration_params_path = camera_calibration_params_path
            if mocked_counts_path is not None:
                with open(mocked_counts_path) as f:
                    self.mocked_counts = json.load(f)
                self.validate_mocked_counts()
        else:
            self.__load_params_from_dotenv(dotenv_path)
            

        self.jpeg = TurboJPEG(self.turbo_jpeg_library_path)
        sio = socketio.Server(async_mode='threading')
        self.sio = sio
        self.app = Flask(__name__, 
                    static_url_path='', 
                    static_folder='static',
                    template_folder='templates')
        CORS(self.app)
        self.app.wsgi_app = socketio.Middleware(self.sio, self.app.wsgi_app)

        if self.camera_calibration_params_path is not None:
            with np.load(self.camera_calibration_params_path) as data:
                self.camera_mtx = data.get('camera_matrix')
                self.dist_coeffs = data.get('dist_coeffs')

            self.new_camera_mtx, self.roi = cv2.getOptimalNewCameraMatrix(self.camera_mtx, self.dist_coeffs, (self.width, self.height), 0)
            self.map1, self.map2 = cv2.initUndistortRectifyMap(self.camera_mtx, self.dist_coeffs, None, self.new_camera_mtx, (self.width, self.height), cv2.CV_16SC2)
        else:
            self.map1, self.map2 = None, None

        self.reset_counter = False

        self.num_of_frames = 0
        self.num_of_frames_with_jpeg_encode = 0
        self.num_of_frames_with_base64_encode = 0

        self.avg_frame_time = 0
        self.avg_total_frame_time = 0
        self.avg_fps = 0
        self.avg_waiting_for_frame_time = 0
        self.avg_total_inferencing_tracking_count_time = 0
        self.avg_frame_decode_time = 0
        self.avg_jpeg_encode_time = 0
        self.avg_base64_encode_time = 0
        self.avg_socket_emit_time = 0
        self.avg_undistortion_time = 0

        self.showing_video = self.force_transmit_video

        @sio.on('connect')
        def test_connect(sid, msg):
            print('Client connected')

        @sio.on('disconnect')
        def test_disconnect(sid):
            print('Client disconnected')

        @sio.on('test')
        def test(sid, msg):
            print(f'Test {msg}')

        @sio.on('reset-count')
        def reset_counter(sid, msg):
            print(f'reset count {msg}')
            self.reset_counter = True

        @sio.on('set-video')
        def set_video(sid, msg):
            print(f'set video {msg}')
            if not self.force_transmit_video:
                self.showing_video = bool(msg)

    def __load_params_from_dotenv(self, dotenv_path = './.env'):
        load_dotenv(dotenv_path)
        height_from_env = environ.get('HEIGHT')
        if height_from_env == None or not height_from_env.isdigit():
            self.height = 1080
        else:
            self.height = int(height_from_env)

        width_from_env = environ.get('WIDTH')
        if width_from_env == None or not width_from_env.isdigit():
            self.width = 1920
        else:
            self.width = int(width_from_env)

        camera_id_from_env = environ.get('CAMERA_ID')
        if camera_id_from_env == None or not camera_id_from_env.isdigit():
            self.camera_id = 0
        else:
            self.camera_id = int(camera_id_from_env)

        camera_fps_from_env = environ.get('CAMERA_FPS')
        if camera_fps_from_env == None or not camera_fps_from_env.isdigit():
            self.camera_fps = 60
        else:
            self.camera_fps = int(camera_fps_from_env)

        region_width_from_env = environ.get('COUNTING_REGION_WIDTH_PERCENTAGE')
        if region_width_from_env == None or not region_width_from_env.replace('.','',1).isdigit():
            self.counting_region_width_percentage = 0.4
        else:
            self.counting_region_width_percentage = float(region_width_from_env)

        self.model_path = environ.get('MODEL_PATH')

        model_imgsiz_from_env = environ.get('MODEL_IMGSZ')
        if model_imgsiz_from_env == None or not model_imgsiz_from_env.isdigit():
            self.model_imgsz = 1440
        else:
            self.model_imgsz = int(model_imgsiz_from_env)

        frame_encode_quality_from_env = environ.get('FRAME_ENCODE_QUALITY')
        if frame_encode_quality_from_env == None or not frame_encode_quality_from_env.isdigit():
            self.frame_encode_quality = 85
        else:
            self.frame_encode_quality = max(min(int(frame_encode_quality_from_env), 100), 0)

        self.render_debug_count = environ.get('RENDER_DEBUG_COUNT') == 'true'

        self.print_debug_performance_metrics = environ.get('PRINT_DEBUG_PERFORMANCE_METRICS') == 'true'

        self.turbo_jpeg_library_path = environ.get('TURBO_JPEG_LIBRARY_PATH')

        self.camera_calibration_params_path = environ.get('CAMERA_CALIBRATION_PARAMS_PATH')

        if environ.get('MOCKED_COUNTS_PATH') is not None:
            with open(environ.get('MOCKED_COUNTS_PATH')) as f:
                self.mocked_counts = json.load(f)
            self.validate_mocked_counts()

    def validate_mocked_counts(self):
        invalid_batches = []
        for index, batch in enumerate(self.mocked_counts):
            total = batch.get('total')
            classwise: dict[str, int] = batch.get('classwise')

            classwise_total = sum(classwise.values())

            if total != classwise_total:
                invalid_batches.append({ 'index': index, 'expected_total': total, 'actual': classwise_total })
        if len(invalid_batches) > 0:
            print('Invalid mocked counts!')
            print(invalid_batches)
            sys.exit(-1)

    def calculate_frame_time_data(
            self,
            frame_time: int,
            total_frame_time: int,
            waiting_for_frame_time: int,
            total_inferencing_tracking_count_time: int,
            frame_decode_time: int,
            socket_emit_time: int,
            jpeg_encode_time: int = None,
            base64_encode_time: int = None,
            undistortion_time: int = None,
            print_data = False

    ):  
        self.avg_frame_time = ((self.avg_frame_time * self.num_of_frames) + frame_time) / (self.num_of_frames + 1)
        self.avg_total_frame_time = ((self.avg_total_frame_time * self.num_of_frames) + total_frame_time) / (self.num_of_frames + 1)
        self.avg_fps = 1000 / self.avg_total_frame_time
        self.avg_waiting_for_frame_time = ((self.avg_waiting_for_frame_time * self.num_of_frames) + waiting_for_frame_time) / (self.num_of_frames + 1)
        self.avg_total_inferencing_tracking_count_time = ((self.avg_total_inferencing_tracking_count_time * self.num_of_frames) + total_inferencing_tracking_count_time) / (self.num_of_frames + 1)
        self.avg_frame_decode_time = ((self.avg_frame_decode_time * self.num_of_frames) + frame_decode_time) / (self.num_of_frames + 1)

        if undistortion_time is not None:
            self.avg_undistortion_time = ((self.avg_undistortion_time * self.num_of_frames) + undistortion_time) / (self.num_of_frames + 1)

        if jpeg_encode_time is not None:
            self.avg_jpeg_encode_time = ((self.avg_jpeg_encode_time * self.num_of_frames_with_jpeg_encode) + jpeg_encode_time) / (self.num_of_frames_with_jpeg_encode + 1)
            self.num_of_frames_with_jpeg_encode += 1

        if base64_encode_time is not None:
            self.avg_base64_encode_time = ((self.avg_base64_encode_time * self.num_of_frames_with_base64_encode) + base64_encode_time) / (self.num_of_frames_with_base64_encode + 1)
            self.num_of_frames_with_base64_encode += 1
        
        self.avg_socket_emit_time = ((self.avg_socket_emit_time * self.num_of_frames) + socket_emit_time) / (self.num_of_frames + 1)
        self.num_of_frames += 1

        if print_data:
            print(f'''avg fps: {self.avg_fps:0.2f}, avg_frame_time: {self.avg_frame_time:0.2f} ms, avg_total_frame_time: {self.avg_total_frame_time:0.2f} ms
avg_waiting_for_frame_time: {self.avg_waiting_for_frame_time:0.2f} ms, avg_total_inferencing_tracking_count_time: {self.avg_total_inferencing_tracking_count_time:0.2f} ms
avg_frame_decode_time: {self.avg_frame_decode_time:0.2f} ms, avg_jpeg_encode_time: {self.avg_jpeg_encode_time:0.2f} ms, avg_base64_encode_time: {self.avg_base64_encode_time:0.2f} ms
avg_socket_emit_time: {self.avg_socket_emit_time:0.2f} ms, avg_undistortion_time: {self.avg_undistortion_time:0.2f} ms
showing_video: {self.showing_video}
''')
        self.sio.emit('frame_time', {
            'num_of_frames': self.num_of_frames,
            'avg_frame_time': self.avg_frame_time,
            'avg_fps': self.avg_fps,
            'avg_total_frame_time': self.avg_total_frame_time,
            'avg_waiting_for_frame_time': self.avg_waiting_for_frame_time,
            'avg_total_inferencing_tracking_count_time': self.avg_total_inferencing_tracking_count_time,
            'avg_frame_decode_time': self.avg_frame_decode_time,
            'avg_jpeg_encode_time': self.avg_jpeg_encode_time,
            'avg_base64_encode_time': self.avg_base64_encode_time,
            'avg_socket_emit_time': self.avg_socket_emit_time,
            'avg_undistortion_time': self.avg_undistortion_time,
        }, namespace='/')

    current_batch_index = 0
    mocked_counts: dict = None
    current_total_count = 0
    count_change_rate: float = 0
    starting_time_count_changed: float = None
    last_time_count_changed: float = None

    def process_counts(self, total_in: int, total_out: int, classwise_count: dict):
        if self.mocked_counts is None:
            return {
                'total_in': total_in,
                'total_out': total_out,
                'class_wise_count': classwise_count
            }
        
        batch_index = self.current_batch_index % len(self.mocked_counts)
        mocked_total_count = self.mocked_counts[batch_index].get('total')
        mocked_total_classwise_counts = self.mocked_counts[batch_index].get('classwise')

        threshold = round(mocked_total_count / 2)
        if self.starting_time_count_changed is None and total_out > 0:
            self.starting_time_count_changed = perf_counter()
            self.last_time_count_changed = perf_counter()

        print(f'count change rate: {self.count_change_rate}')
        
        if total_out < threshold and total_out != self.current_total_count:
            self.current_total_count = min(total_out, threshold)
            self.last_time_count_changed = perf_counter()
            self.count_change_rate = self.current_total_count / (self.last_time_count_changed - self.starting_time_count_changed)


        if total_out >= threshold and self.current_total_count < mocked_total_count:
            seconds_til_next_increment = 1 / (self.count_change_rate * random())
            now = perf_counter()
            seconds_since_last_increment = now - self.last_time_count_changed
            print(f'seconds_til_next_increment: {seconds_til_next_increment}, seconds_since_last_increment: {seconds_since_last_increment}')
            if seconds_since_last_increment >= seconds_til_next_increment:
                self.last_time_count_changed = now
                num_to_increment_by = round(seconds_since_last_increment / seconds_til_next_increment)
                print(f'num_to_increment_by: {num_to_increment_by}')
                self.current_total_count = min(mocked_total_count, self.current_total_count + num_to_increment_by)


        percent_done = self.current_total_count / mocked_total_count
        processed_classwise_counts = {k: { 'IN': 0, 'OUT': round(v * percent_done) } for k, v in mocked_total_classwise_counts.items()}

        return {
            'total_in': total_in,
            'total_out': self.current_total_count,
            'class_wise_count': processed_classwise_counts
        }

    def detection_process(self):
        model = YOLO(self.model_path)
        counter = Counter(model.names, self.width, self.height)

        with Device.from_id(self.camera_id) as cam:
            cam.set_fps(BufferType.VIDEO_CAPTURE, self.camera_fps)
            cam.set_format(BufferType.VIDEO_CAPTURE, self.width, self.height, "MJPG")
            print(cam.get_format(BufferType.VIDEO_CAPTURE))
            end_of_prev_frame = perf_counter_ns()
            print(cam.get_fps(BufferType.VIDEO_CAPTURE))
            for frame in cam:
                start_of_current_frame = perf_counter_ns()
                waiting_for_frame_time = (start_of_current_frame - end_of_prev_frame) / 1_000_000
                try:
                    decoded_frame = self.jpeg.decode(frame.array, flags=TJFLAG_FASTUPSAMPLE|TJFLAG_FASTDCT)
                    after_jpeg_decode = perf_counter_ns()
                    frame_decode_time = (after_jpeg_decode - start_of_current_frame) / 1_000_000
                    if self.map1 is not None and self.map2 is not None:
                        decoded_frame = cv2.remap(decoded_frame, self.map1, None, None)
                        after_undistortion = perf_counter_ns()
                        undistortion_time = (after_undistortion - after_jpeg_decode) / 1_000_000
                    else:
                        undistortion_time = None
                    print(decoded_frame.shape)
                    results = model.predict(decoded_frame)[0]
                    detections = Detections.from_ultralytics(results)
                    decoded_frame, in_count, out_count = counter.trigger(decoded_frame, detections)
                    after_inference = perf_counter_ns()
                    total_inferencing_tracking_count_time = (after_inference - after_jpeg_decode) / 1_000_000
                    classwise_counts = {k: { 'IN': v, 'OUT': 0 } for k, v in counter.category_counts.items()}
                    payload = self.process_counts(in_count, out_count, classwise_counts)

                    if self.showing_video:
                        buffer = self.jpeg.encode(decoded_frame, quality=self.frame_encode_quality)
                        after_jpeg_encode = perf_counter_ns()

                        jpeg_encode_time = (after_jpeg_encode - after_inference) / 1_000_000

                        encoded_frame = base64.b64encode(buffer).decode('utf-8')
                        after_base64_encode = perf_counter_ns()
                        base64_encode_time = (after_base64_encode - after_jpeg_encode) / 1_000_000
                        payload['encoded_frame'] = encoded_frame
                    else:
                        jpeg_encode_time = None
                        base64_encode_time = None

                    self.sio.emit('detection_event', payload, namespace='/')

                    after_socketio_emit = perf_counter_ns()
                    socket_emit_time = (after_socketio_emit - (after_base64_encode if self.showing_video else after_inference)) / 1_000_000
                    
                    current_frame_time = (after_socketio_emit - start_of_current_frame) / 1_000_000
                    total_frame_time = (after_socketio_emit - end_of_prev_frame) / 1_000_000
                    if self.reset_counter:
                        counter.reset_counter()
                        self.current_batch_index += 1
                        self.current_total_count = 0
                        self.starting_time_count_changed = None
                        self.last_time_count_changed = None
                        self.count_change_rate = 0
                        self.reset_counter = False
                    print(f'frame took {total_frame_time:0.2f} ms')
                    self.calculate_frame_time_data(
                        current_frame_time,
                        total_frame_time,
                        waiting_for_frame_time,
                        total_inferencing_tracking_count_time,
                        frame_decode_time,
                        socket_emit_time,
                        jpeg_encode_time,
                        base64_encode_time,
                        undistortion_time=undistortion_time,
                        print_data=self.print_debug_performance_metrics
                    )
                    end_of_prev_frame = perf_counter_ns()
                except Exception as e:
                    print(f'got error {e}')
                    error_traceback = traceback.format_exc()
                    print(error_traceback)
        print('detection process has stopped')

    def run(self):
        with self.app.app_context():
            self.detection_thread = Thread(target=self.detection_process)
            self.detection_thread.daemon = True  # Daemonize thread
            self.detection_thread.start()
        self.app.run(threaded=True)

if __name__ == '__main__':
    print('Is using CUDA: ' + str(torch.cuda.is_available()))
    dotenv_path = './.env'
    if len(sys.argv) > 1:
        dotenv_path = sys.argv[1]
    force_transmit_video = False
    if len(sys.argv) > 2:
        force_transmit_video = sys.argv[2] == 'force-transmit-video'
    counter_app = CounterApp(
        load_params_from_dotenv=True,
        dotenv_path=dotenv_path,
        force_transmit_video=force_transmit_video
    )
    counter_app.run()
