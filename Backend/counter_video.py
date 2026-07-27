import json
from ultralytics import YOLO
from tqdm import tqdm
from os import listdir, environ, makedirs
from os.path import join
import supervision as sv
import torch
from dotenv import load_dotenv
import counter as ctr
import sys
import numpy as np
import cv2

print('Is using CUDA: ' + str(torch.cuda.is_available()))

class CounterVideo:
    def __init__(self,
            load_params_from_dotenv = True,
            height = 1080,
            width = 1920,
            model_path = 'resources/counting-machine-1-category-yolo11.pt',
            category_model_path = 'resources/resnet_v1_18_unscaled.pth',
            model_imgsz = 1440,
            camera_calibration_params_path: str = None,
            counting_algorithm: str = 'yolo_consensus',
            show_output = False,
        ) -> None:
        self.show_output = show_output
        if load_params_from_dotenv:
            self.__load_params_from_dotenv()
        else:
            self.model_path = model_path
            self.height = height
            self.width = width
            self.category_model_path = category_model_path
            self.model_imgsz = model_imgsz
            self.camera_calibration_params_path = camera_calibration_params_path
            self.counting_algorithm = counting_algorithm

        self.model = YOLO(self.model_path)
        self.byte_tracker = sv.ByteTrack()
        self.counter = ctr.Counter(
            self.model.names,
            self.width,
            self.height,
            self.model_path,
            self.category_model_path,
            '',
            counting_algorithm=self.counting_algorithm,
            is_test=True,
        )

        if self.camera_calibration_params_path is not None:
            with np.load(self.camera_calibration_params_path) as data:
                self.camera_mtx = data.get('camera_matrix')
                self.dist_coeffs = data.get('dist_coeffs')

            self.new_camera_mtx, self.roi = cv2.getOptimalNewCameraMatrix(self.camera_mtx, self.dist_coeffs, (self.width, self.height), 0)
            self.map1, self.map2 = cv2.initUndistortRectifyMap(self.camera_mtx, self.dist_coeffs, None, self.new_camera_mtx, (self.width, self.height), cv2.CV_16SC2)
        else:
            self.map1, self.map2 = None, None

    def reset_counter(self):
        self.counter.reset_counter()
        self.byte_tracker.reset()


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

        self.model_path = environ.get('MODEL_PATH')

        self.category_model_path = environ.get('CATEGORY_MODEL_PATH')

        model_imgsiz_from_env = environ.get('MODEL_IMGSZ')
        if model_imgsiz_from_env == None or not model_imgsiz_from_env.isdigit():
            self.model_imgsz = 1440
        else:
            self.model_imgsz = int(model_imgsiz_from_env)

        self.camera_calibration_params_path = environ.get('CAMERA_CALIBRATION_PARAMS_PATH')

        self.counting_algorithm = environ.get('COUNTING_ALGORITHM', 'YOLO_CONSENSUS').lower()

    def bulk_process_directory(self, source_dir: str, dest_dir: str):
        makedirs(dest_dir, exist_ok=True)
        if self.show_output:
            cv2.namedWindow("Counti", cv2.WND_PROP_FULLSCREEN)
            cv2.setWindowProperty("Counti", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        source_videos = listdir(source_dir)

        for i in range(0, len(source_videos)):
            source_video_path = join(source_dir, source_videos[i]) 
            target_video_path = join(dest_dir, source_videos[i])
            self.process_video(source_video_path, target_video_path)

        if self.show_output:
            cv2.destroyAllWindows()
            

    def process_video(self, source_path: str, target_path: str):
        # Open the video file
        cap = cv2.VideoCapture(source_path)

        if not cap.isOpened():
            raise IOError(f"Cannot open video file: {source_path}")
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')  # or use 'XVID', 'mp4v', etc.

        # Open output writer
        out = cv2.VideoWriter(target_path, fourcc, 30, (self.width, self.height))
        frame_idx = 0
        with tqdm(total=100000, desc=f'processing {source_path}') as pbar:
            while True:
                ret, bgr_frame = cap.read()
                if not ret:
                    break  # No more frames or error

                if self.map1 is not None and self.map2 is not None:
                    bgr_frame = cv2.remap(bgr_frame, self.map1, None, None)
                rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
                results = self.model.predict(bgr_frame.copy(), imgsz=self.model_imgsz, agnostic_nms=True, verbose=False)[0]
                detections = sv.Detections.from_ultralytics(results)
                original_class_ids = detections.class_id
                detections.class_id = np.full(original_class_ids.shape, 0)
                detections = self.byte_tracker.update_with_detections(detections)
                detections.class_id = original_class_ids
                annotated_frame, payload = self.counter.trigger(bgr_frame, rgb_frame, detections)

                if self.show_output:
                    cv2.imshow("Counti", annotated_frame)
                    cv2.waitKey(1)

                out.write(annotated_frame)

                frame_idx += 1
                pbar.update()

        cap.release()
        out.release()

        output_json_filename = target_path.replace('.avi', '.json')
        with open(output_json_filename, 'w') as f:
            json.dump(self.counter.current_count(), f, indent=4)
        self.reset_counter()



if __name__ == "__main__":
    counter_video = CounterVideo(show_output=True)
    source_dir = sys.argv[1]
    dest_dir = sys.argv[2]

    counter_video.bulk_process_directory(source_dir, dest_dir)