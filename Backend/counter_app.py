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
from time import sleep, perf_counter_ns
import supervision as sv
from dotenv import load_dotenv

class CounterApp:
    def __init__(self,
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
            turbo_jpeg_library_path: str = None
        ) -> None:

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

        self.jpeg = TurboJPEG(turbo_jpeg_library_path)
        sio = socketio.Server(async_mode='threading')
        self.sio = sio
        self.app = Flask(__name__, 
                    static_url_path='', 
                    static_folder='static',
                    template_folder='templates')
        CORS(self.app)
        self.app.wsgi_app = socketio.Middleware(self.sio, self.app.wsgi_app)

        

        self.reset_counter = False

        self.num_of_frames = 0
        self.num_of_frames_with_jpeg_encode = 0
        self.num_of_frames_with_base64_encode = 0

        self.avg_frame_time = 0
        self.avg_total_frame_time = 0
        self.avg_fps = 0
        self.avg_waiting_for_frame_time = 0
        self.avg_total_inferencing_and_tracking_time = 0
        self.avg_count_time = 0
        self.avg_frame_decode_time = 0
        self.avg_jpeg_encode_time = 0
        self.avg_base64_encode_time = 0
        self.avg_socket_emit_time = 0

        self.showing_video = False

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
            self.showing_video = bool(msg)

    def calculate_frame_time_data(
            self,
            frame_time: int,
            total_frame_time: int,
            waiting_for_frame_time: int,
            total_inferencing_and_tracking_time: int,
            count_time: int,
            frame_decode_time: int,
            socket_emit_time: int,
            jpeg_encode_time: int = None,
            base64_encode_time: int = None,
            print_data = False

    ):  
        self.avg_frame_time = ((self.avg_frame_time * self.num_of_frames) + frame_time) / (self.num_of_frames + 1)
        self.avg_total_frame_time = ((self.avg_total_frame_time * self.num_of_frames) + total_frame_time) / (self.num_of_frames + 1)
        self.avg_fps = 1000 / self.avg_total_frame_time
        self.avg_waiting_for_frame_time = ((self.avg_waiting_for_frame_time * self.num_of_frames) + waiting_for_frame_time) / (self.num_of_frames + 1)
        self.avg_total_inferencing_and_tracking_time = ((self.avg_total_inferencing_and_tracking_time * self.num_of_frames) + total_inferencing_and_tracking_time) / (self.num_of_frames + 1)
        self.avg_count_time = ((self.avg_count_time * self.num_of_frames) + count_time) / (self.num_of_frames + 1)

        self.avg_frame_decode_time = ((self.avg_frame_decode_time * self.num_of_frames) + frame_decode_time) / (self.num_of_frames + 1)

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
avg_waiting_for_frame_time: {self.avg_waiting_for_frame_time:0.2f} ms, avg_total_inferencing_and_tracking_time: {self.avg_total_inferencing_and_tracking_time:0.2f} ms
avg_count_time: {self.avg_count_time:0.2f} ms, avg_frame_decode_time: {self.avg_frame_decode_time:0.2f} ms
avg_jpeg_encode_time: {self.avg_jpeg_encode_time:0.2f} ms, avg_base64_encode_time: {self.avg_base64_encode_time:0.2f} ms, avg_socket_emit_time: {self.avg_socket_emit_time:0.2f} ms
showing_video: {self.showing_video}
''')

    def detection_process(self):
        model = YOLO(self.model_path)

        # Define region points
        region_points = [(int(self.width / 2) - int(self.width * self.counting_region_width_percentage / 2), 0), (int(self.width / 2) + int(self.width * self.counting_region_width_percentage / 2), 0), (int(self.width / 2) + int(self.width * self.counting_region_width_percentage / 2), self.height), (int(self.width / 2) - int(self.width * self.counting_region_width_percentage / 2), self.height)]
        # Init Object Counter
        counter = solutions.ObjectCounter(
            reg_pts=region_points,
            names=model.names,
            draw_tracks=True,
            line_thickness=2,
            view_in_counts=self.render_debug_count,
            view_out_counts=self.render_debug_count
        )

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
                    print(decoded_frame.shape)
                    tracks = model.track(decoded_frame, persist=True, show=False, agnostic_nms=True, imgsz=self.model_imgsz)
                    after_inference = perf_counter_ns()
                    total_inferencing_and_tracking_time = (after_inference - after_jpeg_decode) / 1_000_000

                    decoded_frame = counter.start_counting(decoded_frame, tracks)
                    after_count = perf_counter_ns()
                    count_time = (after_count - after_inference) / 1_000_000

                    payload = {
                        'total_in': counter.in_counts,
                        'total_out': counter.out_counts,
                        'class_wise_count': counter.class_wise_count
                    }

                    if self.showing_video:
                        buffer = self.jpeg.encode(decoded_frame, quality=self.frame_encode_quality)
                        after_jpeg_encode = perf_counter_ns()

                        jpeg_encode_time = (after_jpeg_encode - after_count) / 1_000_000

                        encoded_frame = base64.b64encode(buffer).decode('utf-8')
                        after_base64_encode = perf_counter_ns()
                        base64_encode_time = (after_base64_encode - after_jpeg_encode) / 1_000_000
                        payload['encoded_frame'] = encoded_frame
                    else:
                        jpeg_encode_time = None
                        base64_encode_time = None

                    self.sio.emit('detection_event', payload, namespace='/')

                    after_socketio_emit = perf_counter_ns()
                    socket_emit_time = (after_socketio_emit - (after_base64_encode if self.showing_video else after_count)) / 1_000_000
                    
                    current_frame_time = (after_socketio_emit - start_of_current_frame) / 1_000_000
                    total_frame_time = (after_socketio_emit - end_of_prev_frame) / 1_000_000
                    if self.reset_counter:
                        counter = solutions.ObjectCounter(
                            reg_pts=region_points,
                            names=model.names,
                            draw_tracks=True,
                            line_thickness=2,
                            view_in_counts=self.render_debug_count,
                            view_out_counts=self.render_debug_count
                        )
                        self.reset_counter = False
                    print(f'frame took {total_frame_time:0.2f} ms')
                    self.calculate_frame_time_data(
                        current_frame_time,
                        total_frame_time,
                        waiting_for_frame_time,
                        total_inferencing_and_tracking_time,
                        count_time,
                        frame_decode_time,
                        socket_emit_time,
                        jpeg_encode_time,
                        base64_encode_time,
                        print_data=self.print_debug_performance_metrics
                    )
                    end_of_prev_frame = perf_counter_ns()

                except Exception as e:
                    print(f'got error {e}')

    def run(self):
        with self.app.app_context():
            # Start the detection process in a separate thread
            # Implement additional logic if needed to properly start the detection process
            print("Detection process started.")
            detection_thread = Thread(target=self.detection_process)
            detection_thread.daemon = True  # Daemonize thread
            detection_thread.start()
        self.app.run(threaded=True)

if __name__ == '__main__':
    print('Is using CUDA: ' + str(torch.cuda.is_available()))

    load_dotenv('./.env')

    height_from_env = environ.get('HEIGHT')
    if height_from_env == None or not height_from_env.isdigit():
        height = 1080
    else:
        height = int(height_from_env)

    width_from_env = environ.get('WIDTH')
    if width_from_env == None or not width_from_env.isdigit():
        width = 1920
    else:
        width = int(width_from_env)

    camera_id_from_env = environ.get('CAMERA_ID')
    if camera_id_from_env == None or not camera_id_from_env.isdigit():
        camera_id = 0
    else:
        camera_id = int(camera_id_from_env)

    camera_fps_from_env = environ.get('CAMERA_FPS')
    if camera_fps_from_env == None or not camera_fps_from_env.isdigit():
        camera_fps = 60
    else:
        camera_fps = int(camera_fps_from_env)

    region_width_from_env = environ.get('COUNTING_REGION_WIDTH_PERCENTAGE')
    if region_width_from_env == None or not region_width_from_env.replace('.','',1).isdigit():
        counting_region_width_percentage = 0.4
    else:
        counting_region_width_percentage = float(region_width_from_env)

    model_path = environ.get('MODEL_PATH')

    model_imgsiz_from_env = environ.get('MODEL_IMGSZ')
    if model_imgsiz_from_env == None or not model_imgsiz_from_env.isdigit():
        model_imgsz = 1440
    else:
        model_imgsz = int(model_imgsiz_from_env)

    frame_encode_quality_from_env = environ.get('FRAME_ENCODE_QUALITY')
    if frame_encode_quality_from_env == None or not frame_encode_quality_from_env.isdigit():
        frame_encode_quality = 85
    else:
        frame_encode_quality = max(min(int(frame_encode_quality_from_env), 100), 0)

    render_debug_count = environ.get('RENDER_DEBUG_COUNT') == 'true'

    print_debug_performance_metrics = environ.get('PRINT_DEBUG_PERFORMANCE_METRICS') == 'true'

    turbo_jpeg_library_path = environ.get('TURBO_JPEG_LIBRARY_PATH')

    counter_app = CounterApp(
        height=height,
        width=width,
        camera_id=camera_id,
        camera_fps=camera_fps,
        counting_region_width_percentage=counting_region_width_percentage,
        model_path=model_path,
        model_imgsz=model_imgsz,
        frame_encode_quality=frame_encode_quality,
        render_debug_count=render_debug_count,
        print_debug_performance_metrics=print_debug_performance_metrics,
        turbo_jpeg_library_path=turbo_jpeg_library_path
    )
    counter_app.run()
