from supervision import TraceAnnotator, BoxAnnotator, LabelAnnotator, Detections, ByteTrack, LineZoneAnnotator, LineZone, Point, Position
from utils.overlay_line_zone_annotator import OverlayLineZoneAnnotator
from category_classifier import CategoryClassifier
from datetime import datetime
import numpy as np
import traceback
import uuid
from multiprocessing import Process, Queue, shared_memory
import utils.sqlmodel_db as sqlite_db
import json
from pydantic import BaseModel

category_classes = [
    'can',
    'plastic',
    'drinkbox',
    'gabletop',
    'pouch'
]

IMAGE_BUFFER_SIZE = 30

def save_state_process(data_to_save_queue: Queue, collected_images_dir: str):
    sqlite_db.init_db()
    print('DB INITIALIZED')
    while True:
        try:
            data_to_save = data_to_save_queue.get()
            sqlite_db.save_state(data_to_save, collected_images_dir)
            with open('resources/save_state_success.json', 'w') as f:
                json.dump({ 'message': f'successfully saved {len(data_to_save.multi_container_images_to_save)} multi container images and {len(data_to_save.single_container_images)} single container images' }, f, indent=4)
            print('SUCCESSFULLY SAVED IMAGES')
        except Exception as e:
            print(f'FAILED SAVING IMAGES: {e}')
            print(traceback.format_exc())
            with open('resources/save_state_error.json', 'w') as f:
                json.dump({ 'error': str(e), 'traceback': traceback.format_exc()}, f, indent=4)

class TrackerIdHistory:
    tracker_id: int
    current_majority: int
    weighted_history: np.ndarray
    crossed_center: bool

    def __init__(self, tracker_id: int):
        self.tracker_id = tracker_id
        self.current_majority = 0
        self.weighted_history = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
        self.history = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
        self.crossed_center = False

    def increment(self, class_index, confidence):
        if class_index > 4:
            return
        self.weighted_history[class_index] += confidence
        self.history[class_index] += 1
        self.current_majority = self._get_majority()

    def _get_majority(self):
        return int(np.argmax(self.weighted_history))
    
class TrackerIdPredictionHistogram:
    frame_width: int
    frame_height: int
    histogram: dict[int, TrackerIdHistory]

    def __init__(self, width: int, height: int):
        self.histogram = {}
        self.frame_width = width
        self.frame_height = height

    def get_category_count(self):
        categories = list(map(lambda e: e.current_majority, filter(lambda e: e.crossed_center, self.histogram.values())))
        unique, category_counts = np.unique(categories, return_counts=True)
        category_counts = dict(zip(unique, category_counts))
        return { category: int(category_counts.get(i, 0)) for i, category in enumerate(category_classes) }

    def update_from_detections(self, detections: Detections):
        for tracker_id, class_id, confidence, xyxy in zip(detections.tracker_id, detections.class_id, detections.confidence, detections.xyxy):
            current_history = self.histogram.get(tracker_id)
            if current_history is None:
                current_history = TrackerIdHistory(tracker_id)
                self.histogram[tracker_id] = current_history
            bbox_width = xyxy[2] - xyxy[0]
            bbox_x_center = xyxy[0] + round(bbox_width / 2)
            if bbox_x_center < self.frame_width / 3:
                current_history.current_majority = class_id
            elif bbox_x_center < self.frame_width * 2 / 3:
                current_history.increment(class_id, confidence)

        return self.get_category_count()
    
    def set_tracker_id_crossed_center(self, tracker_ids: np.ndarray):
        for tracker_id in tracker_ids:
            current_history = self.histogram.get(tracker_id)
            if current_history is None:
                current_history = TrackerIdHistory(tracker_id)
                self.histogram[tracker_id] = current_history
            current_history.crossed_center = True
    
    def get_class_for_tracker_id(self, tracker_id: int):
        return self.histogram.get(tracker_id).current_majority
    
    def get_class_conf_for_tracker_id(self, tracker_id: int, current_frame_confidence: float):
        tracker_id_history = self.histogram.get(tracker_id)
        if tracker_id_history.history[tracker_id_history.current_majority] > 0:
            return tracker_id_history.weighted_history[tracker_id_history.current_majority]
        else:
            return current_frame_confidence
    
    def reset(self):
        self.histogram = {}


class AuthorizedUser(BaseModel):
    user_id: str
    user_name: str
    signed_in_time: datetime


class Counter:
    def __init__(
            self,
            names: list[str],
            width: int,
            height: int,
            yolo_model_path: str,
            category_model_path: str,
            collected_images_dir: str,
            counting_algorithm = 'YOLO_CONSENSUS',
            is_test = False,
        ):
        self.is_test = is_test
        self.counting_algorithm = counting_algorithm
        if counting_algorithm.lower() == 'yolo_consensus':
            self.selected_trigger_algorithm = self.yolo_consensus
        else:
            self.selected_trigger_algorithm = self.dual_model_snapshot
        self.width = width
        self.height = height
        self.names = names
        self.yolo_model = yolo_model_path.split('/')[-1]
        self.category_model = category_model_path.split('/')[-1]
        # self.first_line_zone = LineZone(start=Point(self.width * 3 / 4, 0), end=Point(self.width * 3 / 4, self.height), triggering_anchors=[Position.CENTER])
        # self.center_line_zone = LineZone(start=Point(self.width / 2, 0), end=Point(self.width / 2, self.height), triggering_anchors=[Position.CENTER])
        # self.last_line_zone = LineZone(start=Point(self.width / 4, 0), end=Point(self.width / 4, self.height), triggering_anchors=[Position.CENTER])
        self.first_line_zone = LineZone(start=Point(0, self.height * 3 / 4), end=Point(self.width, self.height * 3 / 4), triggering_anchors=[Position.CENTER])
        self.center_line_zone = LineZone(start=Point(0, self.height / 2), end=Point(self.width, self.height / 2), triggering_anchors=[Position.CENTER])
        self.last_line_zone = LineZone(start=Point(0, self.height / 4), end=Point(self.width, self.height / 4), triggering_anchors=[Position.CENTER])
        self.line_zone_annotator = LineZoneAnnotator(text_scale=1, thickness=2, text_thickness=2)
        self.overlay_line_zone_annotator = OverlayLineZoneAnnotator(self.center_line_zone)
        self.box_annotator = BoxAnnotator(thickness=2)
        self.trace_annotator = TraceAnnotator(thickness=2)
        self.label_annotator = LabelAnnotator(text_thickness=2, text_scale=1)
        self.category_classifier = CategoryClassifier(category_model_path)
        self.tracker_id_to_category: dict[int, str] = {}
        self.tracker_id_prediction_histogram = TrackerIdPredictionHistogram(self.width, self.height)
        self.category_counts = {
            'can': 0,
            'plastic': 0,
            'drinkbox': 0,
            'gabletop': 0,
            'pouch': 0
        }
        self.expected_category_counts: dict[str, int] = None

        self.current_batch_multi_container_image_index = 0
        self.current_batch_uuid = uuid.uuid4()
        self.time_batch_started = datetime.now()

        self.first_line_zone_in_count: int = 0
        self.center_line_zone_in_count: int = 0
        self.last_line_zone_in_count: int = 0

        self.last_time_image_collected: datetime = None
        self.last_image_first_line_zone_in_count: int = 0
        self.last_image_center_line_zone_in_count: int = 0
        self.last_image_last_line_zone_in_count: int = 0

        self.data_to_save_queue = Queue()
        self.data_to_save = sqlite_db.DataToSave(multi_container_images_to_save=[], single_container_images=[], batch_submitted=False)
        self.data_to_save_shms: list[shared_memory.SharedMemory] = []
        self.prev_data_to_save: sqlite_db.DataToSave = None
        self.prev_data_to_save_shms: list[shared_memory.SharedMemory] = []
        self.current_express_qr_code: str = None
        self.current_eazy_pickup_tag_id: int = None
        self.current_eazy_pickup_id: str = None
        self.current_eazy_pickup_user_name: str = None
        self.authorized_user: AuthorizedUser = None

        if not self.is_test:
            self.save_state_process = Process(target=save_state_process, args=[self.data_to_save_queue, collected_images_dir])
            self.save_state_process.start()

    def set_expected_count(self, expected_category_counts: dict[str, int]):
        self.expected_category_counts = expected_category_counts

    def current_count(self):
        return {
            'count': self.center_line_zone.in_count,
            'can_count': self.category_counts.get('can'),
            'plastic_count': self.category_counts.get('plastic'),
            'drinkbox_count': self.category_counts.get('drinkbox'),
            'gabletop_count': self.category_counts.get('gabletop'),
            'pouch_count': self.category_counts.get('pouch'),
            'expected_can_count': self.expected_category_counts.get('can') if self.expected_category_counts is not None else None,
            'expected_plastic_count': self.expected_category_counts.get('plastic') if self.expected_category_counts is not None else None,
            'expected_drinkbox_count': self.expected_category_counts.get('drinkbox') if self.expected_category_counts is not None else None,
            'expected_gabletop_count': self.expected_category_counts.get('gabletop') if self.expected_category_counts is not None else None,
            'expected_pouch_count': self.expected_category_counts.get('pouch') if self.expected_category_counts is not None else None,
        }

    def trigger(self, decoded_frame: np.ndarray, rgb_frame: np.ndarray, detections: Detections):
        return self.selected_trigger_algorithm(decoded_frame, rgb_frame, detections)
        
    def dual_model_snapshot(self, decoded_frame: np.ndarray, rgb_frame: np.ndarray, detections: Detections):

        send_data_to_save = False

        # annotated_frame = self.trace_annotator.annotate(
        #     scene=decoded_frame.copy(),
        #     detections=detections)
        # annotated_frame = self.box_annotator.annotate(
        #     scene=annotated_frame,
        #     detections=detections)
        
        self.first_line_zone.trigger(detections)
        center_crossed_in, _ = self.center_line_zone.trigger(detections)
        self.last_line_zone.trigger(detections)

        self.capture_counts()

        if self.should_capture_image() and not self.is_test:
            self.signal_image_captured()
            id = uuid.uuid4()
            shm = shared_memory.SharedMemory(name=str(id), create=True, size=decoded_frame.nbytes)
            shared_arr = np.ndarray(decoded_frame.shape, decoded_frame.dtype, shm.buf)
            np.copyto(shared_arr, decoded_frame)
            self.data_to_save_shms.append(shm)
            self.data_to_save.multi_container_images_to_save.append(
                sqlite_db.MultiContainerImageToSave(
                    detections=detections,
                    image=sqlite_db.MultiContainerImage(
                        id=str(id),
                        index=self.current_batch_multi_container_image_index - 1,
                        time_collected=self.last_time_image_collected,
                        height=decoded_frame.shape[0],
                        width=decoded_frame.shape[1],
                        batch_id=str(self.current_batch_uuid),
                    )
                )
            )

        send_data_to_save = len(self.data_to_save.multi_container_images_to_save) >= IMAGE_BUFFER_SIZE

        center_crossed_in_coords = np.argwhere(center_crossed_in == True)
        if center_crossed_in_coords.shape[0] == 0:
            labels = [
                f"{self.names[class_id] if self.tracker_id_to_category.get(tracker_id) is None else category_classes[self.tracker_id_to_category.get(tracker_id)]} {confidence:0.2f}"
                for confidence, class_id, tracker_id
                in zip(detections.confidence, detections.class_id, detections.tracker_id)
            ]

            # annotated_frame = self.label_annotator.annotate(
            #     scene=annotated_frame,
            #     detections=detections,
            #     labels=labels)

            # annotated_frame = self.line_zone_annotator.annotate(annotated_frame, line_counter=self.center_line_zone)
            
            if send_data_to_save and not self.is_test:
                self.data_to_save.batch = counter_to_batch(self)
                self.data_to_save_queue.put(self.data_to_save)
                self.prev_data_to_save = self.data_to_save
                for shm in self.prev_data_to_save_shms:
                    shm.close()
                    shm.unlink()
                self.prev_data_to_save_shms = self.data_to_save_shms
                self.data_to_save_shms = []
                self.data_to_save = sqlite_db.DataToSave(multi_container_images_to_save=[], single_container_images=[], batch_submitted=False)

            annotated_frame = self.overlay_line_zone_annotator.annotate(decoded_frame.copy(), center_crossed_in, detections, self.center_line_zone.in_count, self.category_counts, labels=labels)

            return annotated_frame, self.current_count()

        try:
            squeeze_axis = 0
            if center_crossed_in_coords.shape[0] > 1:
                squeeze_axis = 1

            xyxy = detections.xyxy[center_crossed_in]
            confidence = np.squeeze(detections.confidence[center_crossed_in_coords], axis=squeeze_axis)
            class_id = np.squeeze(detections.class_id[center_crossed_in_coords].astype(int), axis=squeeze_axis)
            tracker_id = np.squeeze(detections.tracker_id[center_crossed_in_coords].astype(int), axis=squeeze_axis)
            center_crossed_in_detections = Detections(
                    xyxy=xyxy, 
                    confidence=confidence, 
                    class_id=class_id,
                    tracker_id=tracker_id
                )
            
            def crop_bbox_from_frame(xyxy: np.ndarray):
                x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
                bbox = rgb_frame[y1:y2, x1:x2]
                return bbox
            center_crossed_in_bboxes = list(map(crop_bbox_from_frame, center_crossed_in_detections.xyxy))
            categories = self.category_classifier.run_inference(center_crossed_in_bboxes)

            def single_container_image_save(e):
                index, category_index = e
                id = uuid.uuid4()
                frame = center_crossed_in_bboxes[index]
                shm = shared_memory.SharedMemory(name=str(id), create=True, size=frame.nbytes)
                shared_arr = np.ndarray(frame.shape, frame.dtype, shm.buf)
                np.copyto(shared_arr, frame)
                self.data_to_save_shms.append(shm)
                return sqlite_db.SingleContainerImage(
                    id=str(id),
                    time_collected=now,
                    predicted_category=category_classes[category_index],
                    height=frame.shape[0],
                    width=frame.shape[1],
                    tracker_id=int(tracker_id[index]),
                    batch_id=str(self.current_batch_uuid)
                )

            now = datetime.now()
            if not self.is_test:
                self.data_to_save.single_container_images.extend(list(map(single_container_image_save, enumerate(categories))))


            for index, category in enumerate(categories):
                self.tracker_id_to_category[center_crossed_in_detections.tracker_id[index]] = category
            unique, category_counts = np.unique(categories, return_counts=True)
            category_counts = dict(zip(unique, category_counts))
            for class_index, count in category_counts.items():
                self.category_counts[category_classes[class_index]] += int(count)
            
            labels = [
                f"{self.names[class_id] if self.tracker_id_to_category.get(tracker_id) is None else category_classes[self.tracker_id_to_category.get(tracker_id)]} {confidence:0.2f}"
                for confidence, class_id, tracker_id
                in zip(detections.confidence, detections.class_id, detections.tracker_id)
            ]

            # annotated_frame = self.label_annotator.annotate(
            #     scene=annotated_frame,
            #     detections=detections,
            #     labels=labels)

            # annotated_frame = self.line_zone_annotator.annotate(annotated_frame, line_counter=self.center_line_zone)

            annotated_frame = self.overlay_line_zone_annotator.annotate(decoded_frame.copy(), center_crossed_in, detections, self.center_line_zone.in_count, self.category_counts, labels=labels)
            
            send_data_to_save = send_data_to_save or len(self.data_to_save.single_container_images) >= IMAGE_BUFFER_SIZE * 10

            if send_data_to_save and not self.is_test:
                self.data_to_save.batch = counter_to_batch(self)
                self.data_to_save_queue.put(self.data_to_save)
                self.prev_data_to_save = self.data_to_save
                for shm in self.prev_data_to_save_shms:
                    shm.close()
                    shm.unlink()
                self.prev_data_to_save_shms = self.data_to_save_shms
                self.data_to_save_shms = []
                self.data_to_save = sqlite_db.DataToSave(multi_container_images_to_save=[], single_container_images=[], batch_submitted=False)

            return annotated_frame, self.current_count()
        except Exception as e:
            print(f'got error in counter trigger: {e}')
            error_traceback = traceback.format_exc()
            print(error_traceback)
            return decoded_frame, self.current_count()

    def yolo_consensus(self, decoded_frame: np.ndarray, rgb_frame: np.ndarray, detections: Detections):
        try:
            send_data_to_save = False
            
            self.first_line_zone.trigger(detections)
            center_crossed_in, _ =  self.center_line_zone.trigger(detections)
            self.last_line_zone.trigger(detections)

            center_crossed_in_coords = np.argwhere(center_crossed_in == True)
            if center_crossed_in_coords.shape[0] != 0:
                squeeze_axis = 0
                if center_crossed_in_coords.shape[0] > 1:
                    squeeze_axis = 1

                tracker_ids = np.squeeze(detections.tracker_id[center_crossed_in_coords].astype(int), axis=squeeze_axis)
                self.tracker_id_prediction_histogram.set_tracker_id_crossed_center(tracker_ids)

            self.category_counts = self.tracker_id_prediction_histogram.update_from_detections(detections)

            self.capture_counts()

            if self.should_capture_image() and not self.is_test:
                self.signal_image_captured()
                id = uuid.uuid4()
                shm = shared_memory.SharedMemory(name=str(id), create=True, size=decoded_frame.nbytes)
                shared_arr = np.ndarray(decoded_frame.shape, decoded_frame.dtype, shm.buf)
                np.copyto(shared_arr, decoded_frame)
                self.data_to_save_shms.append(shm)
                self.data_to_save.multi_container_images_to_save.append(
                    sqlite_db.MultiContainerImageToSave(
                        index=self.current_batch_multi_container_image_index - 1,
                        time=self.last_time_image_collected,
                        detections=detections,
                        frame_shape=decoded_frame.shape,
                        id=id,
                        batch_id=self.current_batch_uuid,
                    )
                )

            annotated_frame = self.trace_annotator.annotate(
                scene=decoded_frame.copy(),
                detections=detections)
            annotated_frame = self.box_annotator.annotate(
                scene=annotated_frame,
                detections=detections)

            labels = [
                f"#{tracker_id} {category_classes[self.tracker_id_prediction_histogram.get_class_for_tracker_id(tracker_id)]} {self.tracker_id_prediction_histogram.get_class_conf_for_tracker_id(tracker_id, confidence):0.2f}"
                for confidence, class_id, tracker_id
                in zip(detections.confidence, detections.class_id, detections.tracker_id)
            ]

            annotated_frame = self.label_annotator.annotate(
                scene=annotated_frame,
                detections=detections,
                labels=labels)

            annotated_frame = self.line_zone_annotator.annotate(annotated_frame, line_counter=self.center_line_zone)
            
            send_data_to_save = len(self.data_to_save.multi_container_images_to_save) >= IMAGE_BUFFER_SIZE

            if send_data_to_save and not self.is_test:
                self.data_to_save.batch = counter_to_batch(self)
                self.data_to_save_queue.put(self.data_to_save)
                self.prev_data_to_save = self.data_to_save
                for shm in self.prev_data_to_save_shms:
                    shm.close()
                    shm.unlink()
                self.prev_data_to_save_shms = self.data_to_save_shms
                self.data_to_save_shms = []
                self.data_to_save = sqlite_db.DataToSave(multi_container_images_to_save=[], single_container_images=[], batch_submitted=False)

            return annotated_frame, self.current_count()
        except Exception as e:
            print(f'got error in counter trigger: {e}')
            error_traceback = traceback.format_exc()
            print(error_traceback)
            return decoded_frame, self.current_count()
    
    def should_capture_image(self):
        if self.last_time_image_collected is not None and (datetime.now() - self.last_time_image_collected).total_seconds() < 0.5:
            return False
        
        if max(self.get_count_differences()) >= 2:
            return True
        
        return False

    def get_count_differences(self):
        return [
            self.first_line_zone_in_count - self.last_image_first_line_zone_in_count, 
            self.center_line_zone_in_count - self.last_image_center_line_zone_in_count,
            self.last_line_zone_in_count - self.last_image_last_line_zone_in_count
        ]

    def capture_counts(self):
        self.first_line_zone_in_count = self.first_line_zone.in_count
        self.center_line_zone_in_count = self.center_line_zone.in_count
        self.last_line_zone_in_count = self.last_line_zone.in_count

    def signal_image_captured(self):
        self.last_time_image_collected = datetime.now()
        self.current_batch_multi_container_image_index += 1
        self.last_image_first_line_zone_in_count = self.first_line_zone_in_count
        self.last_image_center_line_zone_in_count = self.center_line_zone_in_count
        self.last_image_last_line_zone_in_count = self.last_line_zone_in_count

    def reset_counter(self):
        batch = counter_to_batch(self, submitted=True)
        self.data_to_save.batch = batch
        self.data_to_save.batch_submitted = True
        self.current_express_qr_code = None
        self.current_eazy_pickup_tag_id = None
        self.current_eazy_pickup_id = None
        self.current_eazy_pickup_user_name = None
        save_to_db = self.center_line_zone.in_count > 3
        # self.first_line_zone = LineZone(start=Point(self.width * 3 / 4, 0), end=Point(self.width * 3 / 4, self.height), triggering_anchors=[Position.CENTER])
        # self.center_line_zone = LineZone(start=Point(self.width / 2, 0), end=Point(self.width / 2, self.height), triggering_anchors=[Position.CENTER])
        # self.last_line_zone = LineZone(start=Point(self.width / 4, 0), end=Point(self.width / 4, self.height), triggering_anchors=[Position.CENTER])
        self.first_line_zone = LineZone(start=Point(0, self.height * 3 / 4), end=Point(self.width, self.height * 3 / 4), triggering_anchors=[Position.CENTER])
        self.center_line_zone = LineZone(start=Point(0, self.height / 2), end=Point(self.width, self.height / 2), triggering_anchors=[Position.CENTER])
        self.last_line_zone = LineZone(start=Point(0, self.height / 4), end=Point(self.width, self.height / 4), triggering_anchors=[Position.CENTER])
        self.overlay_line_zone_annotator.reset()
        self.category_counts = {
            'can': 0,
            'plastic': 0,
            'drinkbox': 0,
            'gabletop': 0,
            'pouch': 0
        }
        self.tracker_id_prediction_histogram.reset()
        self.tracker_id_to_category = {}

        self.current_batch_multi_container_image_index = 0
        self.time_batch_started = datetime.now()
        self.current_batch_uuid = uuid.uuid4()

        self.first_line_zone_in_count = 0
        self.center_line_zone_in_count = 0
        self.last_line_zone_in_count = 0

        self.last_time_image_collected = None
        self.last_image_first_line_zone_in_count = 0
        self.last_image_center_line_zone_in_count = 0
        self.last_image_last_line_zone_in_count = 0

        if not self.is_test and save_to_db:
            self.data_to_save_queue.put(self.data_to_save)
        self.prev_data_to_save = self.data_to_save
        if not self.is_test:
            for shm in self.prev_data_to_save_shms:
                        shm.close()
                        shm.unlink()
        self.prev_data_to_save_shms = self.data_to_save_shms
        self.data_to_save_shms = []
        self.data_to_save = sqlite_db.DataToSave(multi_container_images_to_save=[], single_container_images=[], batch_submitted=False)
        return batch if save_to_db else None


def counter_to_batch(counter: Counter, submitted = False):
        return sqlite_db.Batch(
            id=str(counter.current_batch_uuid),
            express_qr_code=counter.current_express_qr_code,
            eazy_pickup_id=counter.current_eazy_pickup_id,
            time_started=counter.time_batch_started,
            time_submitted=datetime.now() if submitted else None,
            count=counter.center_line_zone.in_count,
            can_count=counter.category_counts.get('can'),
            plastic_count=counter.category_counts.get('plastic'),
            drinkbox_count=counter.category_counts.get('drinkbox'),
            gabletop_count=counter.category_counts.get('gabletop'),
            pouch_count=counter.category_counts.get('pouch'),
            expected_count=sum(list(map(lambda e: e[1], counter.expected_category_counts.items()))) if counter.expected_category_counts is not None else None,
            expected_can_count=counter.expected_category_counts.get('can') if counter.expected_category_counts is not None else None,
            expected_plastic_count=counter.expected_category_counts.get('plastic') if counter.expected_category_counts is not None else None,
            expected_drinkbox_count=counter.expected_category_counts.get('drinkbox') if counter.expected_category_counts is not None else None,
            expected_gabletop_count=counter.expected_category_counts.get('gabletop') if counter.expected_category_counts is not None else None,
            expected_pouch_count=counter.expected_category_counts.get('pouch') if counter.expected_category_counts is not None else None,
            yolo_model=counter.yolo_model,
            category_model=counter.category_model,
            authorized_user_id=counter.authorized_user.user_id if counter.authorized_user is not None else None
        )