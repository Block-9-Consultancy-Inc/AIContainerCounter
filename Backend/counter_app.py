from flask import Flask, jsonify
from flask.json.provider import DefaultJSONProvider
from os import environ
import socketio
import base64
from threading import Thread
from ultralytics import YOLO
from turbojpeg import TurboJPEG, TJFLAG_FASTUPSAMPLE, TJFLAG_FASTDCT
from flask_cors import CORS
import torch
from linuxpy.video.device import Device, BufferType
from time import perf_counter_ns
from dotenv import load_dotenv
import sys
import cv2
import numpy as np
import traceback
from supervision import Detections
import counter as ctr
from utils.sqlite_db import Batch, get_day_summary, get_today_summary
from playhouse.shortcuts import model_to_dict
from datetime import datetime
import json
import uuid
from utils.button_listener import ButtonListener

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
            force_transmit_video = False,
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
            only_use_yolo_model: bool = False,
            button_listener_serial_port: str = None
        ) -> None:

        self.force_transmit_video = force_transmit_video

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
            self.only_use_yolo_model = only_use_yolo_model
            self.button_listener_serial_port = button_listener_serial_port
        else:
            self.__load_params_from_dotenv(dotenv_path)
            

        self.jpeg = TurboJPEG(self.turbo_jpeg_library_path)
        self.app = Flask(__name__, 
                    static_folder='images',
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
        self.avg_frame_decode_time = 0
        self.avg_jpeg_encode_time = 0
        self.avg_base64_encode_time = 0
        self.avg_socket_emit_time = 0
        self.avg_undistortion_time = 0

        self.showing_video = self.force_transmit_video

        @sio.on('connect')
        def on_connect(sid, msg):
            print('Client connected')
            now = datetime.now()
            batches = list(Batch.select().where((Batch.time_submitted != None) & (Batch.time_started.year == now.year) & (Batch.time_started.month == now.month) & (Batch.time_started.day == now.day)).order_by(Batch.time_started).dicts())
            today_summary = get_today_summary().__dict__
            self.sio.emit('batches_state', {'summary': today_summary, 'batches': batches, 'update_summary': False})


        @sio.on('disconnect')
        def on_disconnect(sid):
            print('Client disconnected')

        @sio.on('test')
        def on_test(sid, msg):
            print(f'Test {msg}')

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
            if not self.force_transmit_video:
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

        self.only_use_yolo_model = environ.get('ONLY_USE_YOLO_MODEL') == 'true'

        self.button_listener_serial_port = environ.get('BUTTON_LISTENER_SERIAL_PORT')

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

        if self.num_of_frames % 1000 == 0:
            print(f'''avg fps: {self.avg_fps:0.2f}, avg_frame_time: {self.avg_frame_time:0.2f} ms, avg_total_frame_time: {self.avg_total_frame_time:0.2f} ms
avg_waiting_for_frame_time: {self.avg_waiting_for_frame_time:0.2f} ms, avg_total_inferencing_tracking_count_time: {self.avg_total_inferencing_tracking_count_time:0.2f} ms
avg_frame_decode_time: {self.avg_frame_decode_time:0.2f} ms, avg_jpeg_encode_time: {self.avg_jpeg_encode_time:0.2f} ms, avg_base64_encode_time: {self.avg_base64_encode_time:0.2f} ms
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
            self.avg_frame_decode_time = 0
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
            'avg_frame_decode_time': self.avg_frame_decode_time,
            'avg_jpeg_encode_time': self.avg_jpeg_encode_time,
            'avg_base64_encode_time': self.avg_base64_encode_time,
            'avg_socket_emit_time': self.avg_socket_emit_time,
            'avg_undistortion_time': self.avg_undistortion_time,
        }, namespace='/')

    def detection_process(self):
        model = YOLO(self.model_path)
        counter = ctr.Counter(
            model.names,
            self.width,
            self.height,
            self.model_path,
            self.category_model_path,
            only_use_yolo_model=self.only_use_yolo_model
        )

        with Device.from_id(self.camera_id) as cam:
            cam.set_fps(BufferType.VIDEO_CAPTURE, self.camera_fps)
            cam.set_format(BufferType.VIDEO_CAPTURE, self.width, self.height, "MJPG")
            print(f'cam format: {cam.get_format(BufferType.VIDEO_CAPTURE)}')
            end_of_prev_frame = perf_counter_ns()
            print(f'cam fps: {cam.get_fps(BufferType.VIDEO_CAPTURE)}')
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
                    results = model.predict(decoded_frame, imgsz=self.model_imgsz, verbose=False)[0]
                    detections = Detections.from_ultralytics(results)
                    decoded_frame, payload = counter.trigger(decoded_frame, detections)
                    after_inference = perf_counter_ns()
                    total_inferencing_tracking_count_time = (after_inference - after_jpeg_decode) / 1_000_000

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
                    if self.set_expected_count:
                        counter.set_expected_count(self.new_expected_count)
                        self.new_expected_count = None
                        self.set_expected_count = False
                    if self.reset_counter:
                        today_summary = get_today_summary()
                        batch = counter.reset_counter()
                        self.reset_counter = False
                        self.sio.emit('batches_state', { 'summary': today_summary.__dict__, 'batches': [model_to_dict(batch)], 'update_summary': True})
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
