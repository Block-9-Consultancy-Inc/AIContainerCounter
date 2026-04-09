import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from utils.gstreamer_app import GStreamerApp, get_numpy_from_buffer
from flask import Flask
from flask.json.provider import DefaultJSONProvider
from os import environ
import socketio
import base64
from threading import Thread
from ultralytics import YOLO
from turbojpeg import TurboJPEG
from flask_cors import CORS
import torch
from time import perf_counter_ns
from dotenv import load_dotenv
import sys
import cv2
import numpy as np
import traceback
from supervision import Detections
import counter as ctr
from utils.sqlite_db import Batch, get_today_summary
from playhouse.shortcuts import model_to_dict
from datetime import datetime
import json
import uuid
from utils.button_listener import ButtonListener
import os

class CustomJSONEncoder(json.JSONEncoder):
    """ Special json encoder """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

class ISODateTimeJSONProvider(DefaultJSONProvider):
    def __init__(self, app):
        super().__init__(app)

    @staticmethod
    def default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return DefaultJSONProvider.default(obj)

class CounterApp:
    def __init__(self,
            load_params_from_dotenv = True,
            dotenv_path = './.env',
            height = 1080,
            width = 1920,
            camera_id = 0,
            camera_fps = 60,
            model_path = 'resources/counting-machine-1-category-yolo11.pt',
            category_model_path = 'resources/resnet_v1_18_unscaled.pth',
            model_imgsz = 1440,
            frame_encode_quality = 85,
            turbo_jpeg_library_path: str = None,
            camera_calibration_params_path: str = None,
            counting_algorithm: str = 'yolo_consensus',
            button_listener_serial_port: str = None,
            is_test: bool = False,
            raw_video_footage_dir = './data',
            collected_images_dir = './images',
        ) -> None:

        self.is_test = is_test
        if not load_params_from_dotenv:
            self.height = height
            self.width = width
            self.camera_id = camera_id
            self.camera_fps = camera_fps
            self.model_path = model_path
            self.category_model_path = category_model_path
            self.model_imgsz = model_imgsz
            self.frame_encode_quality = frame_encode_quality
            self.turbo_jpeg_library_path = turbo_jpeg_library_path
            self.camera_calibration_params_path = camera_calibration_params_path
            self.counting_algorithm = counting_algorithm
            self.button_listener_serial_port = button_listener_serial_port
            self.is_test = is_test
            self.raw_video_footage_dir = raw_video_footage_dir
            self.collected_images_dir = collected_images_dir
        else:
            self.__load_params_from_dotenv(dotenv_path)
            
        os.makedirs(self.raw_video_footage_dir, exist_ok=True)
        os.makedirs(self.collected_images_dir, exist_ok=True)
        self.jpeg = TurboJPEG(self.turbo_jpeg_library_path)

        self.app = Flask(__name__, 
                    static_folder=self.collected_images_dir,
                    static_url_path='/images',
                    template_folder='templates')
        self.app.json = ISODateTimeJSONProvider(self.app)
        sio = socketio.Server(async_mode='threading', json=self.app.json)
        self.sio = sio
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
        self.set_expected_count = False
        self.new_expected_count: dict[str, int] = None

        self.num_of_frames = 0
        self.num_of_frames_with_jpeg_encode = 0
        self.num_of_frames_with_base64_encode = 0

        self.avg_frame_time = 0
        self.avg_total_frame_time = 0
        self.avg_fps = 0
        self.avg_waiting_for_frame_time = 0
        self.avg_total_inferencing_tracking_count_time = 0
        self.avg_jpeg_encode_time = 0
        self.avg_base64_encode_time = 0
        self.avg_socket_emit_time = 0
        self.avg_undistortion_time = 0

        self.showing_video = self.is_test

        self.model = YOLO(self.model_path)
        self.counter = ctr.Counter(
            self.model.names,
            self.width,
            self.height,
            self.model_path,
            self.category_model_path,
            self.collected_images_dir,
            counting_algorithm=self.counting_algorithm,
            is_test=self.is_test,
        )

        @sio.on('connect')
        def on_connect(sid, msg):
            print('Client connected')


        @sio.on('disconnect')
        def on_disconnect(sid):
            print('Client disconnected')

        @sio.on('init-prev-batches')
        def on_test(sid, msg):
            now = datetime.now()
            batches = list(Batch.select().where((Batch.time_submitted != None) & (Batch.time_started.year == now.year) & (Batch.time_started.month == now.month) & (Batch.time_started.day == now.day)).order_by(Batch.time_started).dicts())
            today_summary = get_today_summary().__dict__
            self.sio.emit('batches_state', {'summary': today_summary, 'batches': batches, 'update_summary': False})

        @sio.on('reset-count')
        def reset_counter(sid, msg):
            print(f'reset count {msg}')
            self.reset_counter = True

        @sio.on('set-expected-count')
        def set_expected_count(sid, msg):
            print(f'setting expected count {msg}')
            self.new_expected_count = msg
            self.set_expected_count = True

        @sio.on('clear-expected-count')
        def set_expected_count(sid, msg):
            print(f'setting expected count {msg}')
            self.new_expected_count = None
            self.set_expected_count = True


        @sio.on('set-video')
        def set_video(sid, msg):
            print(f'set video {msg}')
            if not self.is_test:
                self.showing_video = bool(msg)

        @sio.on('get-batch-details')
        def get_batch_details(sid, msg):
            sio.emit('batch_details_state', model_to_dict(Batch.get_by_id(msg), backrefs=True))

        if self.button_listener_serial_port is not None:
            def on_button_pressed(button_id: int):
                print(f'{button_id} pressed!')
                if button_id == 1:
                    self.reset_counter = True
                self.sio.emit('button_pressed_state', button_id)
            self.button_listener = ButtonListener(on_button_pressed, self.button_listener_serial_port)
        
        self.gstreamer_app = CounterGstreamerApp(f'{self.raw_video_footage_dir}/{str(self.counter.current_batch_uuid)}.avi', f'/dev/video{self.camera_id}', self.width, self.height, self.camera_fps, self)
        self.collect_raw_frame = True
        self.end_of_prev_frame = perf_counter_ns()

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

        self.model_path = environ.get('MODEL_PATH')

        self.category_model_path = environ.get('CATEGORY_MODEL_PATH')

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

        self.turbo_jpeg_library_path = environ.get('TURBO_JPEG_LIBRARY_PATH')

        self.camera_calibration_params_path = environ.get('CAMERA_CALIBRATION_PARAMS_PATH')

        self.counting_algorithm = environ.get('COUNTING_ALGORITHM', 'YOLO_CONSENSUS').lower()

        self.button_listener_serial_port = environ.get('BUTTON_LISTENER_SERIAL_PORT')

        self.raw_video_footage_dir = environ.get('RAW_VIDEO_FOOTAGE_DIR', './data')
        self.collected_images_dir = environ.get('COLLECTED_IMAGES_DIR', './images')

    def calculate_frame_time_data(
            self,
            frame_time: int,
            total_frame_time: int,
            waiting_for_frame_time: int,
            total_inferencing_tracking_count_time: int,
            socket_emit_time: int,
            jpeg_encode_time: int = None,
            base64_encode_time: int = None,
            undistortion_time: int = None,
    ):  
        self.avg_frame_time = ((self.avg_frame_time * self.num_of_frames) + frame_time) / (self.num_of_frames + 1)
        self.avg_total_frame_time = ((self.avg_total_frame_time * self.num_of_frames) + total_frame_time) / (self.num_of_frames + 1)
        self.avg_fps = 1000 / self.avg_total_frame_time
        self.avg_waiting_for_frame_time = ((self.avg_waiting_for_frame_time * self.num_of_frames) + waiting_for_frame_time) / (self.num_of_frames + 1)
        self.avg_total_inferencing_tracking_count_time = ((self.avg_total_inferencing_tracking_count_time * self.num_of_frames) + total_inferencing_tracking_count_time) / (self.num_of_frames + 1)

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

        if self.num_of_frames % 1000 == 0 and not self.is_test:
            print(f'''avg fps: {self.avg_fps:0.2f}, avg_frame_time: {self.avg_frame_time:0.2f} ms, avg_total_frame_time: {self.avg_total_frame_time:0.2f} ms
avg_waiting_for_frame_time: {self.avg_waiting_for_frame_time:0.2f} ms, avg_total_inferencing_tracking_count_time: {self.avg_total_inferencing_tracking_count_time:0.2f} ms
avg_jpeg_encode_time: {self.avg_jpeg_encode_time:0.2f} ms, avg_base64_encode_time: {self.avg_base64_encode_time:0.2f} ms
avg_socket_emit_time: {self.avg_socket_emit_time:0.2f} ms, avg_undistortion_time: {self.avg_undistortion_time:0.2f} ms
''')
            self.num_of_frames = 0
            self.num_of_frames_with_jpeg_encode = 0
            self.num_of_frames_with_base64_encode = 0

            self.avg_frame_time = 0
            self.avg_total_frame_time = 0
            self.avg_fps = 0
            self.avg_waiting_for_frame_time = 0
            self.avg_total_inferencing_tracking_count_time = 0
            self.avg_jpeg_encode_time = 0
            self.avg_base64_encode_time = 0
            self.avg_socket_emit_time = 0
            self.avg_undistortion_time = 0
            
        self.sio.emit('frame_time', {
            'num_of_frames': self.num_of_frames,
            'avg_frame_time': self.avg_frame_time,
            'avg_fps': self.avg_fps,
            'avg_total_frame_time': self.avg_total_frame_time,
            'avg_waiting_for_frame_time': self.avg_waiting_for_frame_time,
            'avg_total_inferencing_tracking_count_time': self.avg_total_inferencing_tracking_count_time,
            'avg_jpeg_encode_time': self.avg_jpeg_encode_time,
            'avg_base64_encode_time': self.avg_base64_encode_time,
            'avg_socket_emit_time': self.avg_socket_emit_time,
            'avg_undistortion_time': self.avg_undistortion_time,
        }, namespace='/')

    def detection_frame_process(self, rgb_frame: np.ndarray):
        start_of_current_frame = perf_counter_ns()
        waiting_for_frame_time = (start_of_current_frame - self.end_of_prev_frame) / 1_000_000
        try:
            if self.map1 is not None and self.map2 is not None:
                rgb_frame = cv2.remap(rgb_frame, self.map1, None, None)
                after_undistortion = perf_counter_ns()
                undistortion_time = (after_undistortion - start_of_current_frame) / 1_000_000
            else:
                undistortion_time = None
                after_undistortion = None
            bgr_frame = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
            results = self.model.predict(bgr_frame, imgsz=self.model_imgsz, verbose=False)[0]
            detections = Detections.from_ultralytics(results)
            self.collect_raw_frame = len(detections) > 0
            bgr_frame, payload = self.counter.trigger(bgr_frame, rgb_frame, detections)
            after_inference = perf_counter_ns()
            total_inferencing_tracking_count_time = (after_inference - (after_undistortion if after_undistortion is not None else start_of_current_frame)) / 1_000_000

            if self.showing_video:
                buffer = self.jpeg.encode(bgr_frame, quality=self.frame_encode_quality)
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
            total_frame_time = (after_socketio_emit - self.end_of_prev_frame) / 1_000_000
            if self.set_expected_count:
                self.counter.set_expected_count(self.new_expected_count)
                self.new_expected_count = None
                self.set_expected_count = False
            if self.reset_counter:
                today_summary = get_today_summary()
                batch = self.counter.reset_counter()
                self.reset_counter = False
                self.sio.emit('batches_state', { 'summary': today_summary.__dict__, 'batches': [model_to_dict(batch)], 'update_summary': True})
                self.gstreamer_app.signal_new_file()
                if self.is_test:
                    self.num_of_frames = 0
                    self.num_of_frames_with_jpeg_encode = 0
                    self.num_of_frames_with_base64_encode = 0
                    self.avg_frame_time = 0
                    self.avg_total_frame_time = 0
                    self.avg_fps = 0
                    self.avg_waiting_for_frame_time = 0
                    self.avg_total_inferencing_tracking_count_time = 0
                    self.avg_jpeg_encode_time = 0
                    self.avg_base64_encode_time = 0
                    self.avg_socket_emit_time = 0
                    self.avg_undistortion_time = 0
            self.calculate_frame_time_data(
                current_frame_time,
                total_frame_time,
                waiting_for_frame_time,
                total_inferencing_tracking_count_time,
                socket_emit_time,
                jpeg_encode_time,
                base64_encode_time,
                undistortion_time=undistortion_time,
            )
            self.end_of_prev_frame = perf_counter_ns()
        except Exception as e:
            print(f'got error {e}')
            error_traceback = traceback.format_exc()
            print(error_traceback)

    def run(self):
        with self.app.app_context():
            self.detection_thread = Thread(target=self.gstreamer_app.run)
            self.detection_thread.daemon = True  # Daemonize thread
            self.detection_thread.start()
        self.app.run(host='0.0.0.0', port=5000, threaded=True)

def counter_callback(pad, info, counter_app: CounterApp):
    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK
    
    frame = get_numpy_from_buffer(buffer, 'RGB', 1920, 1080)

    # TODO yolo possibly requires BGR while category models require RGB, look into and find solution

    counter_app.detection_frame_process(frame)

    return Gst.PadProbeReturn.OK

def data_collection_callback(pad, info, counter_app: CounterApp):
    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK
        
    if counter_app.collect_raw_frame:
        return Gst.PadProbeReturn.OK
    else:
        return Gst.PadProbeReturn.DROP

def new_location_callback(splitmux, fragment_id, counter_app: CounterApp):
    return f'{counter_app.raw_video_footage_dir}/{str(counter_app.counter.current_batch_uuid)}.avi'
    
class CounterGstreamerApp(GStreamerApp):
    def __init__(self, first_file_name: str, video_source: str, width: int, height: int, fps: int, user_data: CounterApp):
        super().__init__(first_file_name, video_source, width, height, fps, user_data)
        self.collect_raw_frames = not user_data.is_test
        self.app_callback = counter_callback
        self.data_collection_callback = data_collection_callback
        self.new_location_callback = new_location_callback
        self.create_pipeline()


if __name__ == '__main__':
    print('Is using CUDA: ' + str(torch.cuda.is_available()))
    dotenv_path = './.env'
    if len(sys.argv) > 1:
        dotenv_path = sys.argv[1]
    is_test = False
    if len(sys.argv) > 2:
        is_test = sys.argv[2] == 'test'
    counter_app = CounterApp(
        load_params_from_dotenv=True,
        dotenv_path=dotenv_path,
        is_test=is_test
    )
    counter_app.run()
