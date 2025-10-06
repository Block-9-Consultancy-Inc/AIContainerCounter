from flask import Flask
from os import environ
import socketio
import base64
from threading import Thread
from ultralytics import YOLO, solutions
import cv2
from flask_cors import CORS
import torch
from linuxpy.video.device import Device, BufferType
from time import sleep

print('Is using CUDA: ' + str(torch.cuda.is_available()))

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
    MODEL_PATH = "general-model-1-9.pt"

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

    with Device.from_id(0) as cam:
        cam.set_format(BufferType.VIDEO_CAPTURE, WIDTH, HEIGHT, "MJPG")
        cam.set_fps(BufferType.VIDEO_CAPTURE, 60)
        print(cam.get_format(BufferType.VIDEO_CAPTURE))
        for frame in cam:
            decoded_frame = cv2.imdecode(frame.array, cv2.IMREAD_UNCHANGED)
            print(decoded_frame.shape)
            tracks = model.track(decoded_frame, persist=True, show=False, agnostic_nms=True)

            decoded_frame = counter.start_counting(decoded_frame, tracks)

            metadata = {}
            _, buffer = cv2.imencode('.jpg', decoded_frame)
            metadata['encoded_frame'] = base64.b64encode(buffer).decode('utf-8')
            metadata['total_in'] = counter.in_counts
            metadata['total_out'] = counter.out_counts
            metadata['class_wise_counts'] = counter.class_wise_count

            sio.emit('detection_event', metadata, namespace='/')
        #     # sleep(3)

@sio.on('connect')
def test_connect(sid, msg):
    print('Client connected')

@sio.on('disconnect')
def test_disconnect(sid):
    print('Client disconnected')

@sio.on('test')
def test(sid, msg):
    print(f'Test {msg}')

if __name__ == '__main__':
    with app.app_context():
        # Start the detection process in a separate thread
        # Implement additional logic if needed to properly start the detection process
        print("Detection process started.")
        detection_thread = Thread(target=detection_process)
        detection_thread.daemon = True  # Daemonize thread
        detection_thread.start()
    app.run(threaded=True)
