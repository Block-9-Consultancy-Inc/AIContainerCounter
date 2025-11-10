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


print('Is using CUDA: ' + str(torch.cuda.is_available()))

jpeg = TurboJPEG()
sio = socketio.Server(async_mode='threading')
app = Flask(__name__, 
            static_url_path='', 
            static_folder='static',
            template_folder='templates')
CORS(app)
app.config['SECRET_KEY'] = 'secret!'
app.wsgi_app = socketio.Middleware(sio, app.wsgi_app)

load_dotenv('./.env')

height_from_env = environ.get('HEIGHT')
if height_from_env == None or not height_from_env.isdigit():
    HEIGHT = 720
else:
    HEIGHT = int(height_from_env)

width_from_env = environ.get('WIDTH')
if width_from_env == None or not width_from_env.isdigit():
    WIDTH = 1280
else:
    WIDTH = int(width_from_env)

camera_fps_from_env = environ.get('CAMERA_FPS')
if camera_fps_from_env == None or not camera_fps_from_env.isdigit():
    CAMERA_FPS = 60
else:
    CAMERA_FPS = int(camera_fps_from_env)

region_width_from_env = environ.get('COUNTING_REGION_WIDTH_PERCENTAGE')
if region_width_from_env == None or not region_width_from_env.isdecimal():
    COUNTING_REGION_WIDTH_PERCENTAGE = 0.4
else:
    COUNTING_REGION_WIDTH_PERCENTAGE = float(region_width_from_env)

MODEL_PATH = environ.get('MODEL_PATH')
if MODEL_PATH == None:
    MODEL_PATH = "720-model.pt"

model_imgsiz_from_env = environ.get('MODEL_IMGSZ')
if model_imgsiz_from_env == None or not model_imgsiz_from_env.isdigit():
    MODEL_IMGSZ = 720
else:
    MODEL_IMGSZ = int(model_imgsiz_from_env)

frame_encode_quality_from_env = environ.get('FRAME_ENCODE_QUALITY')
if frame_encode_quality_from_env == None or not frame_encode_quality_from_env.isdigit():
    FRAME_ENCODE_QUALITY = 85
else:
    FRAME_ENCODE_QUALITY = max(min(int(frame_encode_quality_from_env), 100), 0)

RENDER_DEBUG_COUNT = environ.get('RENDER_DEBUG_COUNT') == 'true'

DEBUG_VIDEO = environ.get('DEBUG_VIDEO') == 'true'
SOURCE_VIDEO = environ.get('SOURCE_VIDEO')
if SOURCE_VIDEO == None:
    SOURCE_VIDEO = "test-video (4).mp4"

PRINT_DEBUG_PERFORMANCE_METRICS = environ.get('PRINT_DEBUG_PERFORMANCE_METRICS') == 'true'

reset_counter = False

num_of_frames = 0
num_of_frames_with_jpeg_encode = 0
num_of_frames_with_base64_encode = 0

avg_frame_time = 0
avg_total_frame_time = 0
avg_fps = 0
avg_waiting_for_frame_time = 0
avg_total_inferencing_and_tracking_time = 0
avg_count_time = 0
avg_frame_decode_time = 0
avg_jpeg_encode_time = 0
avg_base64_encode_time = 0
avg_socket_emit_time = 0

showing_video = False

def print_frame_time_data(
        frame_time: int,
        total_frame_time: int,
        waiting_for_frame_time: int,
        total_inferencing_and_tracking_time: int,
        count_time: int,
        frame_decode_time: int,
        socket_emit_time: int,
        jpeg_encode_time: int = None,
        base64_encode_time: int = None

):  
    global avg_frame_time, avg_total_frame_time, avg_fps, avg_waiting_for_frame_time, avg_total_inferencing_and_tracking_time, avg_count_time, avg_frame_decode_time, avg_jpeg_encode_time, avg_base64_encode_time, avg_socket_emit_time, num_of_frames, num_of_frames_with_jpeg_encode, num_of_frames_with_base64_encode
    avg_frame_time = ((avg_frame_time * num_of_frames) + frame_time) / (num_of_frames + 1)
    avg_total_frame_time = ((avg_total_frame_time * num_of_frames) + total_frame_time) / (num_of_frames + 1)
    avg_fps = 1000 / avg_total_frame_time
    avg_waiting_for_frame_time = ((avg_waiting_for_frame_time * num_of_frames) + waiting_for_frame_time) / (num_of_frames + 1)
    avg_total_inferencing_and_tracking_time = ((avg_total_inferencing_and_tracking_time * num_of_frames) + total_inferencing_and_tracking_time) / (num_of_frames + 1)
    avg_count_time = ((avg_count_time * num_of_frames) + count_time) / (num_of_frames + 1)

    avg_frame_decode_time = ((avg_frame_decode_time * num_of_frames) + frame_decode_time) / (num_of_frames + 1)

    if jpeg_encode_time is not None:
        avg_jpeg_encode_time = ((avg_jpeg_encode_time * num_of_frames_with_jpeg_encode) + jpeg_encode_time) / (num_of_frames_with_jpeg_encode + 1)
        num_of_frames_with_jpeg_encode += 1

    if base64_encode_time is not None:
        avg_base64_encode_time = ((avg_base64_encode_time * num_of_frames_with_base64_encode) + base64_encode_time) / (num_of_frames_with_base64_encode + 1)
        num_of_frames_with_base64_encode += 1
    
    avg_socket_emit_time = ((avg_socket_emit_time * num_of_frames) + socket_emit_time) / (num_of_frames + 1)
    num_of_frames += 1

    print(f'''avg fps: {avg_fps:0.2f}, avg_frame_time: {avg_frame_time:0.2f} ms, avg_total_frame_time: {avg_total_frame_time:0.2f} ms
avg_waiting_for_frame_time: {avg_waiting_for_frame_time:0.2f} ms, avg_total_inferencing_and_tracking_time: {avg_total_inferencing_and_tracking_time:0.2f} ms
avg_count_time: {avg_count_time:0.2f} ms, avg_frame_decode_time: {avg_frame_decode_time:0.2f} ms
avg_jpeg_encode_time: {avg_jpeg_encode_time:0.2f} ms, avg_base64_encode_time: {avg_base64_encode_time:0.2f} ms, avg_socket_emit_time: {avg_socket_emit_time:0.2f} ms
showing_video: {showing_video}
''')

    

def extract_frames(video_path):
    # load the VideoReader
    return sv.get_video_frames_generator(video_path)

def detection_process():
    model = YOLO(MODEL_PATH)

    # Define region points
    region_points = [(int(WIDTH / 2) - int(WIDTH * COUNTING_REGION_WIDTH_PERCENTAGE / 2), 0), (int(WIDTH / 2) + int(WIDTH * COUNTING_REGION_WIDTH_PERCENTAGE / 2), 0), (int(WIDTH / 2) + int(WIDTH * COUNTING_REGION_WIDTH_PERCENTAGE / 2), HEIGHT), (int(WIDTH / 2) - int(WIDTH * COUNTING_REGION_WIDTH_PERCENTAGE / 2), HEIGHT)]
    # Init Object Counter
    counter = solutions.ObjectCounter(
        reg_pts=region_points,
        names=model.names,
        draw_tracks=True,
        line_thickness=2,
        view_in_counts=RENDER_DEBUG_COUNT,
        view_out_counts=RENDER_DEBUG_COUNT
    )

    global reset_counter
    global showing_video
    if DEBUG_VIDEO:
        while True:
            generator = extract_frames(SOURCE_VIDEO)
            time_counter = perf_counter_ns()
            for frame in generator:
                decoded_frame = frame
                print(decoded_frame.shape)
                tracks = model.track(decoded_frame, persist=True, show=False, agnostic_nms=True, imgsz=MODEL_IMGSZ)

                decoded_frame = counter.start_counting(decoded_frame, tracks)

                buffer = jpeg.encode(decoded_frame, quality=FRAME_ENCODE_QUALITY)
                sio.emit('detection_event', {
                    'encoded_frame': base64.b64encode(buffer).decode('utf-8'),
                    'total_in': counter.in_counts,
                    'total_out': counter.out_counts,
                    'class_wise_count': counter.class_wise_count
                }, namespace='/')
                current_time = perf_counter_ns()
                current_frame_time = (current_time - time_counter) / 1_000_000
                if reset_counter:
                    counter = solutions.ObjectCounter(
                        reg_pts=region_points,
                        names=model.names,
                        draw_tracks=True,
                        line_thickness=2,
                        view_in_counts=RENDER_DEBUG_COUNT,
                        view_out_counts=RENDER_DEBUG_COUNT
                    )
                    reset_counter = False
                print(f'frame took {current_frame_time:0.2f} ms')
                # sleep(3)
                time_counter = perf_counter_ns()
    else:
        with Device.from_id(0) as cam:
            cam.set_fps(BufferType.VIDEO_CAPTURE, CAMERA_FPS)
            cam.set_format(BufferType.VIDEO_CAPTURE, WIDTH, HEIGHT, "MJPG")
            print(cam.get_format(BufferType.VIDEO_CAPTURE))
            end_of_prev_frame = perf_counter_ns()
            print(cam.get_fps(BufferType.VIDEO_CAPTURE))
            for frame in cam:
                start_of_current_frame = perf_counter_ns()
                waiting_for_frame_time = (start_of_current_frame - end_of_prev_frame) / 1_000_000
                try:
                    decoded_frame = jpeg.decode(frame.array, flags=TJFLAG_FASTUPSAMPLE|TJFLAG_FASTDCT)
                    after_jpeg_decode = perf_counter_ns()
                    frame_decode_time = (after_jpeg_decode - start_of_current_frame) / 1_000_000
                    print(decoded_frame.shape)
                    tracks = model.track(decoded_frame, persist=True, show=False, agnostic_nms=True, imgsz=MODEL_IMGSZ)
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

                    if showing_video:
                        buffer = jpeg.encode(decoded_frame, quality=FRAME_ENCODE_QUALITY)
                        after_jpeg_encode = perf_counter_ns()

                        jpeg_encode_time = (after_jpeg_encode - after_count) / 1_000_000

                        encoded_frame = base64.b64encode(buffer).decode('utf-8')
                        after_base64_encode = perf_counter_ns()
                        base64_encode_time = (after_base64_encode - after_jpeg_encode) / 1_000_000
                        payload['encoded_frame'] = encoded_frame
                    else:
                        jpeg_encode_time = None
                        base64_encode_time = None

                    sio.emit('detection_event', payload, namespace='/')

                    after_socketio_emit = perf_counter_ns()
                    socket_emit_time = (after_socketio_emit - (after_base64_encode if showing_video else after_count)) / 1_000_000
                    
                    current_frame_time = (after_socketio_emit - start_of_current_frame) / 1_000_000
                    total_frame_time = (after_socketio_emit - end_of_prev_frame) / 1_000_000
                    if reset_counter:
                        counter = solutions.ObjectCounter(
                            reg_pts=region_points,
                            names=model.names,
                            draw_tracks=True,
                            line_thickness=2,
                            view_in_counts=RENDER_DEBUG_COUNT,
                            view_out_counts=RENDER_DEBUG_COUNT
                        )
                        reset_counter = False
                    print(f'frame took {total_frame_time:0.2f} ms')
                    if PRINT_DEBUG_PERFORMANCE_METRICS:
                        print_frame_time_data(
                            current_frame_time,
                            total_frame_time,
                            waiting_for_frame_time,
                            total_inferencing_and_tracking_time,
                            count_time,
                            frame_decode_time,
                            socket_emit_time,
                            jpeg_encode_time,
                            base64_encode_time
                        )
                    end_of_prev_frame = perf_counter_ns()

                except Exception as e:
                    print(f'got error {e}')

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
    global reset_counter
    reset_counter = True

@sio.on('set-video')
def set_video(sid, msg):
    print(f'set video {msg}')
    global showing_video
    showing_video = bool(msg)

if __name__ == '__main__':
    with app.app_context():
        # Start the detection process in a separate thread
        # Implement additional logic if needed to properly start the detection process
        print("Detection process started.")
        detection_thread = Thread(target=detection_process)
        detection_thread.daemon = True  # Daemonize thread
        detection_thread.start()
    app.run(threaded=True)
