import json
from ultralytics import YOLO, solutions
from tqdm import tqdm
from os import listdir, environ
from os.path import join
import supervision as sv
import torch
print('Is using CUDA: ' + str(torch.cuda.is_available()))

HEIGHT = 1920
WIDTH = 1080

COUNTING_REGION_WIDTH_PERCENTAGE = 0.4

MODEL_PATH = environ.get('MODEL_PATH')
if MODEL_PATH == None:
    MODEL_PATH = "general-model-1-9.pt"

SOURCE_VIDEO_DIR_PATH = 'test_video_input'
TARGET_VIDEO_DIR_PATH = 'test_video_output'


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

    source_videos = listdir(SOURCE_VIDEO_DIR_PATH)

    for i in range(0, len(source_videos)):
        source_video_path = join(SOURCE_VIDEO_DIR_PATH, source_videos[i]) 
        target_video_path = join(TARGET_VIDEO_DIR_PATH, source_videos[i]) 
        video_info = sv.VideoInfo.from_video_path(source_video_path)
        generator = sv.get_video_frames_generator(source_video_path)
        with sv.VideoSink(target_video_path, video_info) as sink:
            for frame in tqdm(generator, total=video_info.total_frames):
                tracks = model.track(frame.copy(), persist=True, agnostic_nms=True)

                processed_frame = counter.start_counting(frame.copy(), tracks)
                
                sink.write_frame(processed_frame)

if __name__ == "__main__":
    main()