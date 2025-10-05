import cv2
from linuxpy.video.device import Device, BufferType
from ultralytics import YOLO, solutions
# import numpy as np
from os import environ
import torch
print('Is using CUDA: ' + str(torch.cuda.is_available()))


HEIGHT = 1280
WIDTH = 720

COUNTING_REGION_WIDTH_PERCENTAGE = 0.4

MODEL_PATH = environ.get('MODEL_PATH')
if MODEL_PATH == None:
    MODEL_PATH = "general-model-1-9.pt"

def main():
    model = YOLO(MODEL_PATH)

    # Define region points
    region_points = [(int(HEIGHT / 2) - int(WIDTH * COUNTING_REGION_WIDTH_PERCENTAGE / 2), 0), (int(HEIGHT / 2) + int(WIDTH * COUNTING_REGION_WIDTH_PERCENTAGE / 2), 0), (int(HEIGHT / 2) + int(WIDTH * COUNTING_REGION_WIDTH_PERCENTAGE / 2), WIDTH), (int(HEIGHT / 2) - int(WIDTH * COUNTING_REGION_WIDTH_PERCENTAGE / 2), WIDTH)]

    # Init Object Counter
    counter = solutions.ObjectCounter(
        reg_pts=region_points,
        names=model.names,
        draw_tracks=True,
        line_thickness=2,
    )

    with Device.from_id(0) as cam:
        cam.set_format(BufferType.VIDEO_CAPTURE, HEIGHT, WIDTH, "MJPG")
        for frame in cam:
            decoded_frame = cv2.imdecode(frame.array, cv2.IMREAD_UNCHANGED)
            tracks = model.track(decoded_frame, persist=True, agnostic_nms=True)

            decoded_frame = counter.start_counting(decoded_frame, tracks)
            
            if (cv2.waitKey(30) == 27):
                print('manually broke out of capture loop')
                break

    cam.close()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
