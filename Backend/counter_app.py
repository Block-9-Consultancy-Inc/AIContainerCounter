import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from utils.gstreamer_app import GStreamerApp, get_numpy_from_buffer
from flask import Flask
from flask.json.provider import DefaultJSONProvider
from os import environ
import socketio
import base64
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
from supervision import Detections, ByteTrack
import counter as ctr
from utils.sqlite_db import Batch, get_today_summary
from playhouse.shortcuts import model_to_dict
from datetime import datetime, timedelta
import json
import uuid
from utils.button_listener import ButtonListener
import os
from enum import Enum

class PipelineFrameLatencies:
    '''The latencies for the current frame in the pipeline. Each step is in order of appearance in the class.'''
    waiting_for_frame: float = 0.0
    get_frame_from_buffer: float = 0.0
    undistortion: float | None = None
    inference: float = 0.0
    tracking: float = 0.0
    counting: float = 0.0
    jpeg_encode: float | None = None
    base64_encode: float | None = None
    socketio_emit: float = 0.0
    frame_time: float = 0.0
    overall_frame_time: float = 0.0

class AvgPipelineFrameLatencies(PipelineFrameLatencies):
    num_of_frames: int = 0
    num_of_frames_with_video_emitting: int = 0
    fps: float = 0.0

    def add_frame(self, frame: PipelineFrameLatencies):
        self.waiting_for_frame = ((self.waiting_for_frame * self.num_of_frames) + frame.waiting_for_frame) / (self.num_of_frames + 1)
        self.get_frame_from_buffer = ((self.get_frame_from_buffer * self.num_of_frames) + frame.get_frame_from_buffer) / (self.num_of_frames + 1)

        if frame.undistortion is not None:
            self.undistortion = (((0 if self.undistortion is None else self.undistortion) * self.num_of_frames) + frame.undistortion) / (self.num_of_frames + 1)

        self.inference = ((self.inference * self.num_of_frames) + frame.inference) / (self.num_of_frames + 1)
        self.tracking = ((self.tracking * self.num_of_frames) + frame.tracking) / (self.num_of_frames + 1)
        self.counting = ((self.counting * self.num_of_frames) + frame.counting) / (self.num_of_frames + 1)

        if frame.jpeg_encode is not None:
            self.jpeg_encode = (((0 if self.jpeg_encode is None else self.jpeg_encode) * self.num_of_frames_with_video_emitting) + frame.jpeg_encode) / (self.num_of_frames_with_video_emitting + 1)

        if frame.base64_encode is not None:
            self.base64_encode = (((0 if self.base64_encode is None else self.base64_encode) * self.num_of_frames_with_video_emitting) + frame.base64_encode) / (self.num_of_frames_with_video_emitting + 1)
        
        if frame.jpeg_encode is not None or frame.base64_encode is not None:
            self.num_of_frames_with_video_emitting += 1

        self.socketio_emit = ((self.socketio_emit * self.num_of_frames) + frame.socketio_emit) / (self.num_of_frames + 1)
        self.frame_time = ((self.frame_time * self.num_of_frames) + frame.frame_time) / (self.num_of_frames + 1)
        self.overall_frame_time = ((self.overall_frame_time * self.num_of_frames) + frame.overall_frame_time) / (self.num_of_frames + 1)
        self.fps = 1000 / self.overall_frame_time
        self.num_of_frames += 1


    def dump(self) -> dict[str, str]:
        return {
            'waiting_for_frame': self.waiting_for_frame,
            'get_frame_from_buffer': self.get_frame_from_buffer,
            'undistortion': self.undistortion,
            'inference': self.inference,
            'tracking': self.tracking,
            'counting': self.counting,
            'jpeg_encode': self.jpeg_encode,
            'base64_encode': self.base64_encode,
            'socketio_emit': self.socketio_emit,
            'frame_time': self.frame_time,
            'overall_frame_time': self.overall_frame_time,
            'fps': self.fps,
            'num_of_frames': self.num_of_frames,
            'num_of_frames_with_video_emitting': self.num_of_frames_with_video_emitting
        }
    def __repr__(self):
        return f'''avg fps: {self.fps:0.2f}, avg_frame_time: {self.frame_time:0.2f} ms, avg_overall_frame_time: {self.overall_frame_time:0.2f} ms
    avg_waiting_for_frame_time: {self.waiting_for_frame:0.2f} ms, avg_get_frame_from_buffer: {self.get_frame_from_buffer} ms
    avg_undistortion_time: {(self.undistortion if self.undistortion is not None else 0):0.2f} ms, avg_inference_time: {self.inference:0.2f} ms
    avg_tracking_time: {self.tracking:0.2f} ms, avg_counting_time: {self.counting:0.2f} ms
    avg_jpeg_encode_time: {(self.jpeg_encode if self.jpeg_encode is not None else 0):0.2f} ms, avg_base64_encode_time: {(self.base64_encode if self.base64_encode is not None else 0):0.2f} ms
    avg_socketio_emit_time: {self.socketio_emit:0.2f} ms, num_of_frames: {self.num_of_frames}, num_of_frames_with_video_emitting: {self.num_of_frames_with_video_emitting}
    '''
        





class DetectionStatus(Enum):
    RUNNING = 0
    STOPPED = 1
    PAUSED = 2
    SHOWED = 3
    DISAPPEARED = 4

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
            host = '0.0.0.0',
            port = 5000,
        ) -> None:

        self.last_time_detection_showed = datetime.now()
        self.last_time_detection_disappeared = datetime.now()
        self.last_time_detection_paused = datetime.now()
        self.last_time_detection_played = datetime.now()
        self.detection_status = DetectionStatus.STOPPED


        try:
            os.remove('test.socket')
        except:
            pass
        self.is_test = is_test

        self.set_auto_start_pause_handling = self.dummy_auto_start_pause_handling if self.is_test else self.auto_start_pause_handling

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
            self.host = host
            self.port = port
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

        self.avg_frame_latencies = AvgPipelineFrameLatencies()

        self.current_test_case = None
        self.showing_video = self.is_test

        self.model = YOLO(self.model_path)
        self.byte_tracker = ByteTrack()
        # self.byte_tracker = ByteTrack(minimum_consecutive_frames=5, minimum_matching_threshold=0.7)
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

        def on_state_changed(new_state, error=None, debug=None):
            self.sio.emit('pipeline_state', { 'new_state': new_state, 'error': str(error) if error is not None else None, 'debug': str(debug) if debug is not None else None })

        def on_stopped():
            today_summary = get_today_summary()
            batch = self.counter.reset_counter()
            self.gstreamer_app.first_file_path = f'{self.raw_video_footage_dir}/{str(self.counter.current_batch_uuid)}.avi'
            if batch is not None:
                self.sio.emit('batches_state', { 'summary': today_summary.__dict__, 'batches': [model_to_dict(batch)], 'update_summary': True})
            self.avg_frame_latencies = AvgPipelineFrameLatencies()

        self.gstreamer_app = CounterGstreamerApp(on_state_changed, on_stopped, f'{self.raw_video_footage_dir}/{str(self.counter.current_batch_uuid)}.avi', f'/dev/video{self.camera_id}', self.width, self.height, self.camera_fps, self)

        @sio.on('connect')
        def on_connect(sid, msg):
            self.sio.emit('pipeline_state', { 'new_state': self.gstreamer_app.status, 'error': None, 'debug': None })
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

        @sio.on('new-test-case')
        def new_test_case(sid, msg):
            self.current_test_case = msg

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

        @sio.on('pause')
        def pause_pipeline(sid, msg):
            print(f'pausing')
            self.detection_status = DetectionStatus.STOPPED
            self.gstreamer_app.pause()

        @sio.on('stop')
        def stop_pipeline(sid, msg):
            print(f'stopping')
            self.detection_status = DetectionStatus.STOPPED
            self.gstreamer_app.stop()

        @sio.on('play')
        def play_pipeline(sid, msg):
            print(f'playing')
            self.detection_status = DetectionStatus.RUNNING
            self.gstreamer_app.play()
            self.end_of_prev_frame = perf_counter_ns()

        self.last_time_stop_button_pressed: datetime = None
        self.last_time_reset_button_pressed: datetime = None

        if self.button_listener_serial_port is not None:
            def on_button_pressed(button_id: int):
                print(f'{button_id} pressed!')
                emit_button_pressed_event = True
                if button_id == 1:
                    if self.gstreamer_app.status != 'stopped':
                        last_time_reset_button_pressed = self.last_time_reset_button_pressed
                        self.last_time_reset_button_pressed = datetime.now()
                        if not self.is_test and last_time_reset_button_pressed is None or (self.last_time_reset_button_pressed - last_time_reset_button_pressed).total_seconds() > 2:
                            self.sio.emit('reset_confirmation_state', 'need_reset_confirmation')
                            emit_button_pressed_event = False
                        else:
                            self.reset_counter = True
                    else:
                        emit_button_pressed_event = False
                elif button_id == 3:
                    if self.gstreamer_app.status != 'playing':
                        self.detection_status = DetectionStatus.RUNNING
                        self.gstreamer_app.play()
                    else:
                        self.detection_status = DetectionStatus.STOPPED
                        self.gstreamer_app.pause()
                elif button_id == 4:
                    if self.gstreamer_app.status != 'stopped':
                        last_time_stop_button_pressed = self.last_time_stop_button_pressed
                        self.last_time_stop_button_pressed = datetime.now()
                        if last_time_stop_button_pressed is None or (self.last_time_stop_button_pressed - last_time_stop_button_pressed).total_seconds() > 2:
                            self.sio.emit('stop_confirmation_state', 'need_stop_confirmation')
                            emit_button_pressed_event = False
                        else:
                            self.gstreamer_app.stop()
                    else:
                        emit_button_pressed_event = False
                if emit_button_pressed_event:
                    self.sio.emit('button_pressed_state', button_id)
            self.button_listener = ButtonListener(on_button_pressed, self.button_listener_serial_port)

        self.start_of_current_frame = perf_counter_ns()
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

        self.host = environ.get('HOST', '0.0.0.0')
        self.port = int(environ.get('PORT', '5000'))

    def dummy_auto_start_pause_handling(self, num_of_detections: int):
        return

    def auto_start_pause_handling(self, num_of_detections: int):
        if self.detection_status == DetectionStatus.STOPPED:
            return

        if num_of_detections > 0 and self.detection_status != DetectionStatus.RUNNING:
            if self.detection_status == DetectionStatus.PAUSED:
                self.detection_status = DetectionStatus.SHOWED
                self.last_time_detection_showed = datetime.now()
            elif self.detection_status == DetectionStatus.SHOWED:
                if datetime.now() - self.last_time_detection_showed > unpause_threshold:
                    self.detection_status = DetectionStatus.RUNNING
                    self.last_time_detection_played = datetime.now()
                    self.gstreamer_app.play()
            elif self.detection_status == DetectionStatus.DISAPPEARED:
                self.detection_status = DetectionStatus.RUNNING

        if num_of_detections == 0 and self.detection_status != DetectionStatus.PAUSED:
            if self.detection_status == DetectionStatus.RUNNING:
                self.detection_status = DetectionStatus.DISAPPEARED
                self.last_time_detection_disappeared = datetime.now()
            elif self.detection_status == DetectionStatus.DISAPPEARED:
                if datetime.now() - self.last_time_detection_disappeared > pausing_threshold:
                    self.detection_status = DetectionStatus.PAUSED
                    self.last_time_detection_paused = datetime.now()
                    self.gstreamer_app.pause()
            elif self.detection_status == DetectionStatus.SHOWED:
                self.detection_status = DetectionStatus.PAUSED

    def detection_frame_process(
            self,
            rgb_frame: np.ndarray,
            bgr_frame: np.ndarray,
            detections: Detections,
            frame_latencies: PipelineFrameLatencies,
            after_tracking: int
        ):
        self.set_auto_start_pause_handling(len(detections))
        
        try:
            if self.gstreamer_app.status != 'paused':
                bgr_frame, payload = self.counter.trigger(bgr_frame, rgb_frame, detections)
            else:
                payload = self.counter.current_count()
            if self.is_test and self.current_test_case is not None:
                payload['current_test_case'] = self.current_test_case
            after_counting = perf_counter_ns()
            frame_latencies.counting = (after_counting - after_tracking) / 1_000_000

            if self.showing_video:
                buffer = self.jpeg.encode(bgr_frame, quality=self.frame_encode_quality)
                after_jpeg_encode = perf_counter_ns()

                frame_latencies.jpeg_encode = (after_jpeg_encode - after_counting) / 1_000_000

                encoded_frame = base64.b64encode(buffer).decode('utf-8')
                after_base64_encode = perf_counter_ns()
                frame_latencies.base64_encode = (after_base64_encode - after_jpeg_encode) / 1_000_000
                payload['encoded_frame'] = encoded_frame

            self.sio.emit('detection_event', payload, namespace='/')

            after_socketio_emit = perf_counter_ns()
            frame_latencies.socketio_emit = (after_socketio_emit - (after_base64_encode if self.showing_video else after_counting)) / 1_000_000
            
            frame_latencies.frame_time = (after_socketio_emit - self.start_of_current_frame) / 1_000_000
            frame_latencies.overall_frame_time = (after_socketio_emit - self.end_of_prev_frame) / 1_000_000
            if self.set_expected_count:
                self.counter.set_expected_count(self.new_expected_count)
                self.new_expected_count = None
                self.set_expected_count = False
            if self.reset_counter:
                today_summary = get_today_summary()
                batch = self.counter.reset_counter()
                self.byte_tracker.reset()
                self.reset_counter = False
                if batch is not None:
                    self.sio.emit('batches_state', { 'summary': today_summary.__dict__, 'batches': [model_to_dict(batch)], 'update_summary': True})
                self.gstreamer_app.signal_new_file()
                if self.is_test:
                    self.avg_frame_latencies = AvgPipelineFrameLatencies()
            self.end_of_prev_frame = perf_counter_ns()
            self.avg_frame_latencies.add_frame(frame_latencies)
            if self.avg_frame_latencies.num_of_frames % 300 == 0 and not self.is_test:
                print(self.avg_frame_latencies)
                self.avg_frame_latencies = AvgPipelineFrameLatencies()
                
            self.sio.emit('frame_time', {
                'avg_frame_latencies': self.avg_frame_latencies.dump(),
                'current_test_case': self.current_test_case
            }, namespace='/')
        except Exception as e:
            print(f'got error {e}')
            error_traceback = traceback.format_exc()
            print(error_traceback)

    def run(self):
        if self.is_test:
            self.gstreamer_app.play()
        self.app.run(host=self.host, port=self.port, threaded=True)

pausing_threshold = timedelta(seconds=3)
unpause_threshold = timedelta(milliseconds=400)

def detection_frame_callback(pad, info, counter_app: CounterApp):
    start_of_current_frame = perf_counter_ns()
    frame_latencies = PipelineFrameLatencies()
    counter_app.start_of_current_frame = start_of_current_frame
    frame_latencies.waiting_for_frame = (start_of_current_frame - counter_app.end_of_prev_frame) / 1_000_000

    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK
    
    frame = get_numpy_from_buffer(buffer, 'RGB', counter_app.width, counter_app.height)
    after_get_frame_from_buffer = perf_counter_ns()
    frame_latencies.get_frame_from_buffer = (after_get_frame_from_buffer - start_of_current_frame) / 1_000_000

    # TODO yolo possibly requires BGR while category models require RGB, look into and find solution
    
    if counter_app.map1 is not None and counter_app.map2 is not None:
        rgb_frame = cv2.remap(frame, counter_app.map1, None, None)
        after_undistortion = perf_counter_ns()
        frame_latencies.undistortion = (after_undistortion - after_get_frame_from_buffer) / 1_000_000
    else:
        after_undistortion = None
    bgr_frame = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
    results = counter_app.model.predict(bgr_frame, imgsz=counter_app.model_imgsz, verbose=False)[0]
    detections = Detections.from_ultralytics(results)
    after_inference = perf_counter_ns()
    original_class_ids = detections.class_id
    detections.class_id = np.full(original_class_ids.shape, 0)
    detections = counter_app.byte_tracker.update_with_detections(detections)
    detections.class_id = original_class_ids
    after_tracking = perf_counter_ns()

    frame_latencies.inference = ((after_inference - after_undistortion) if after_undistortion is not None else (after_inference - after_get_frame_from_buffer)) / 1_000_000
    frame_latencies.tracking = (after_tracking - after_inference) / 1_000_000

    counter_app.detection_frame_process(frame, bgr_frame, detections, frame_latencies, after_tracking)

    return Gst.PadProbeReturn.OK

def new_location_callback(splitmux, fragment_id, counter_app: CounterApp):
    return f'{counter_app.raw_video_footage_dir}/{str(counter_app.counter.current_batch_uuid)}.avi'
    
class CounterGstreamerApp(GStreamerApp):
    def __init__(self, on_state_changed, on_stopped, first_file_name: str, video_source: str, width: int, height: int, fps: int, user_data: CounterApp):
        super().__init__(on_state_changed, on_stopped, first_file_name, video_source, width, height, fps, user_data)
        self.collect_raw_frames = not user_data.is_test
        self.app_callback = detection_frame_callback
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
