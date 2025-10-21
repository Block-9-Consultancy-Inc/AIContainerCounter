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

HEIGHT = 1080
WIDTH = 1920

COUNTING_REGION_WIDTH_PERCENTAGE = 0.4

MODEL_PATH = environ.get('MODEL_PATH')
if MODEL_PATH == None:
    MODEL_PATH = "counting-machine-3-categories-yolo11.pt"

DEBUG_VIDEO = environ.get('DEBUG_VIDEO') == 'true'
SOURCE_VIDEO = environ.get('SOURCE_VIDEO')
if SOURCE_VIDEO == None:
    SOURCE_VIDEO = "test-video (4).mp4"

reset_counter = False


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
    )

    global reset_counter
    if DEBUG_VIDEO:
        while True:
            generator = extract_frames(SOURCE_VIDEO)
            time_counter = perf_counter_ns()
            for frame in generator:
                decoded_frame = frame
                print(decoded_frame.shape)
                tracks = model.track(decoded_frame, persist=True, show=False, agnostic_nms=True, imgsz=1440)

                decoded_frame = counter.start_counting(decoded_frame, tracks)

                buffer = jpeg.encode(decoded_frame, quality=85)
                sio.emit('detection_event', {
                    'encoded_frame': base64.b64encode(buffer).decode('utf-8'),
                    'total_in': counter.in_counts,
                    'total_out': counter.out_counts,
                    'class_wise_count': counter.class_wise_count
                }, namespace='/')
                current_time = perf_counter_ns()
                frame_time = (current_time - time_counter) / 1_000_000
                if reset_counter:
                    counter = solutions.ObjectCounter(
                        reg_pts=region_points,
                        names=model.names,
                        draw_tracks=True,
                        line_thickness=2,
                    )
                    reset_counter = False
                print(f'frame took {frame_time:0.2f} ms')
                # sleep(3)
                time_counter = perf_counter_ns()
    else:
        with Device.from_id(0) as cam:
            cam.set_fps(BufferType.VIDEO_CAPTURE, 60)
            cam.set_format(BufferType.VIDEO_CAPTURE, WIDTH, HEIGHT, "MJPG")
            print(cam.get_format(BufferType.VIDEO_CAPTURE))
            time_counter = perf_counter_ns()
            print(cam.get_fps(BufferType.VIDEO_CAPTURE))
            for frame in cam:
                try:
                    decoded_frame = jpeg.decode(frame.array, flags=TJFLAG_FASTUPSAMPLE|TJFLAG_FASTDCT)
                    print(decoded_frame.shape)
                    tracks = model.track(decoded_frame, persist=True, show=False, agnostic_nms=True)

                    decoded_frame = counter.start_counting(decoded_frame, tracks)

                    buffer = jpeg.encode(decoded_frame, quality=85)
                    sio.emit('detection_event', {
                        'encoded_frame': base64.b64encode(buffer).decode('utf-8'),
                        'total_in': counter.in_counts,
                        'total_out': counter.out_counts,
                        'class_wise_count': counter.class_wise_count
                    }, namespace='/')
                    current_time = perf_counter_ns()
                    frame_time = (current_time - time_counter) / 1_000_000
                    if reset_counter:
                        counter = solutions.ObjectCounter(
                            reg_pts=region_points,
                            names=model.names,
                            draw_tracks=True,
                            line_thickness=2,
                        )
                        reset_counter = False
                    print(f'frame took {frame_time:0.2f} ms')
                    # sleep(3)
                    time_counter = perf_counter_ns()
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
def test(sid, msg):
    print(f'reset count {msg}')
    global reset_counter
    reset_counter = True

if __name__ == '__main__':
    with app.app_context():
        # Start the detection process in a separate thread
        # Implement additional logic if needed to properly start the detection process
        print("Detection process started.")
        detection_thread = Thread(target=detection_process)
        detection_thread.daemon = True  # Daemonize thread
        detection_thread.start()
    app.run(threaded=True)
