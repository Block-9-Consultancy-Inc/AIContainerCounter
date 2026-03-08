from supervision import TraceAnnotator, BoxAnnotator, LabelAnnotator, Detections, ByteTrack, LineZoneAnnotator, LineZone, Point, Position
from category_classifier import CategoryClassifier
from datetime import datetime
import numpy as np
import traceback
import uuid
from multiprocessing import Process, Queue
import utils.sqlite_db as sqlite_db
import json

category_classes = [
    'can',
    'plastic',
    'drinkbox',
    'gabletop',
    'pouch'
]

def save_state_process(data_to_save_queue: Queue):
    sqlite_db.init_db()
    while True:
        try:
            data_to_save = data_to_save_queue.get()
            sqlite_db.save_state(data_to_save)
            with open('resources/save_state_success.json', 'w') as f:
                json.dump({ 'message': f'successfully saved {len(data_to_save.multi_container_images)} multi container images and {len(data_to_save.single_container_images)} single container images' }, f, indent=4)
        except Exception as e:
            with open('resources/save_state_error.json', 'w') as f:
                json.dump({ 'error': str(e), 'traceback': traceback.format_exc()}, f, indent=4)

class Counter:
    def __init__(
            self,
            names: list[str],
            width: int,
            height: int,
            yolo_model_path: str,
            category_model_path: str,
            only_use_yolo_model = False
        ):
        self.only_use_yolo_model = only_use_yolo_model
        self.width = width
        self.height = height
        self.names = names
        self.yolo_model = yolo_model_path.split('/')[-1]
        self.category_model = category_model_path.split('/')[-1]
        self.byte_tracker = ByteTrack()
        # self.byte_tracker = ByteTrack(minimum_consecutive_frames=5, minimum_matching_threshold=0.7)
        self.first_line_zone = LineZone(start=Point(self.width * 3 / 4, 0), end=Point(self.width * 3 / 4, self.height), triggering_anchors=[Position.CENTER])
        self.center_line_zone = LineZone(start=Point(self.width / 2, 0), end=Point(self.width / 2, self.height), triggering_anchors=[Position.CENTER])
        self.last_line_zone = LineZone(start=Point(self.width / 4, 0), end=Point(self.width / 4, self.height), triggering_anchors=[Position.CENTER])
        self.line_zone_annotator = LineZoneAnnotator(text_scale=1, thickness=2, text_thickness=2)
        self.box_annotator = BoxAnnotator(thickness=2)
        self.trace_annotator = TraceAnnotator(thickness=2)
        self.label_annotator = LabelAnnotator(text_thickness=2, text_scale=1)
        self.category_classifier = CategoryClassifier(category_model_path)
        self.tracker_id_to_category = {}
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
        self.data_to_save = sqlite_db.DataToSave(multi_container_images=[], single_container_images=[])

        self.save_state_process = Process(target=save_state_process, args=[self.data_to_save_queue])
        self.save_state_process.start()

    def set_expected_count(self, expected_category_counts: dict[str, int]):
        self.expected_category_counts = expected_category_counts

    def trigger(self, decoded_frame: np.ndarray, detections: Detections):

        send_data_to_save = False

        detections = self.byte_tracker.update_with_detections(detections)

        annotated_frame = self.trace_annotator.annotate(
            scene=decoded_frame.copy(),
            detections=detections)
        annotated_frame = self.box_annotator.annotate(
            scene=annotated_frame,
            detections=detections)
        
        self.first_line_zone.trigger(detections)
        center_crossed_in, _ = self.center_line_zone.trigger(detections)
        self.last_line_zone.trigger(detections)

        self.capture_counts()

        if self.should_capture_image():
            self.signal_image_captured()
            self.data_to_save.multi_container_images.append(
                sqlite_db.MultiContainerImageToSave(
                    self.current_batch_multi_container_image_index - 1,
                    self.last_time_image_collected,
                    detections,
                    decoded_frame,
                    uuid.uuid4(),
                    self.current_batch_uuid,
                )
            )

        send_data_to_save = len(self.data_to_save.multi_container_images) >= 5

        annotated_frame = self.line_zone_annotator.annotate(annotated_frame, line_counter=self.center_line_zone)

        if self.only_use_yolo_model:
            self.category_counts = {category_classes[class_id]: class_count for class_id, class_count in self.center_line_zone.in_count_per_class.items()}

            labels = [
                f"#{tracker_id} {self.names[class_id]} {confidence:0.2f}"
                for confidence, class_id, tracker_id
                in zip(detections.confidence, detections.class_id, detections.tracker_id)
            ]

            annotated_frame = self.label_annotator.annotate(
                scene=annotated_frame,
                detections=detections,
                labels=labels)
            
            if send_data_to_save:
                self.data_to_save.batch = counter_to_batch_to_save(self)
                self.data_to_save_queue.put(self.data_to_save)
                self.data_to_save = sqlite_db.DataToSave(multi_container_images=[], single_container_images=[])
            
            return annotated_frame, self.center_line_zone.in_count, self.center_line_zone.out_count

        center_crossed_in_coords = np.argwhere(center_crossed_in == True)
        if center_crossed_in_coords.shape[0] == 0:
            labels = [
                f"#{tracker_id} {self.names[class_id] if self.tracker_id_to_category.get(tracker_id) is None else category_classes[self.tracker_id_to_category.get(tracker_id)]} {confidence:0.2f}"
                for confidence, class_id, tracker_id
                in zip(detections.confidence, detections.class_id, detections.tracker_id)
            ]

            annotated_frame = self.label_annotator.annotate(
                scene=annotated_frame,
                detections=detections,
                labels=labels)
            
            if send_data_to_save:
                self.data_to_save.batch = counter_to_batch_to_save(self)
                self.data_to_save_queue.put(self.data_to_save)
                self.data_to_save = sqlite_db.DataToSave(multi_container_images=[], single_container_images=[])

            return annotated_frame, self.center_line_zone.in_count, self.center_line_zone.out_count

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
                bbox = decoded_frame[y1:y2, x1:x2]
                return bbox
            center_crossed_in_bboxes = list(map(crop_bbox_from_frame, center_crossed_in_detections.xyxy))
            categories = self.category_classifier.run_inference(center_crossed_in_bboxes)

            now = datetime.now()
            self.data_to_save.single_container_images.extend(list(map(lambda e: sqlite_db.SingleContainerImageToSave(
                uuid.uuid4(),
                now,
                category_classes[e[1]],
                center_crossed_in_bboxes[e[0]],
                tracker_id[e[0]],
                self.current_batch_uuid
            ), enumerate(categories))))


            for index, category in enumerate(categories):
                self.tracker_id_to_category[center_crossed_in_detections.tracker_id[index]] = category
            unique, category_counts = np.unique(categories, return_counts=True)
            category_counts = dict(zip(unique, category_counts))
            for class_index, count in category_counts.items():
                self.category_counts[category_classes[class_index]] += int(count)
            
            labels = [
                f"#{tracker_id} {self.names[class_id] if self.tracker_id_to_category.get(tracker_id) is None else category_classes[self.tracker_id_to_category.get(tracker_id)]} {confidence:0.2f}"
                for confidence, class_id, tracker_id
                in zip(detections.confidence, detections.class_id, detections.tracker_id)
            ]

            annotated_frame = self.label_annotator.annotate(
                scene=annotated_frame,
                detections=detections,
                labels=labels)
            
            send_data_to_save = send_data_to_save or len(self.data_to_save.single_container_images) >= 50

            if send_data_to_save:
                self.data_to_save.batch = counter_to_batch_to_save(self)
                self.data_to_save_queue.put(self.data_to_save)
                self.data_to_save = sqlite_db.DataToSave(multi_container_images=[], single_container_images=[])

            return annotated_frame, self.center_line_zone.in_count, self.center_line_zone.out_count
        except Exception as e:
            print(f'got error in counter trigger: {e}')
            error_traceback = traceback.format_exc()
            print(error_traceback)
    
    def should_capture_image(self):
        if self.last_time_image_collected is not None and (datetime.now() - self.last_time_image_collected).total_seconds() < 0.5:
            return False
        
        if max(self.get_count_differences()) >= 3:
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
        self.data_to_save.batch = counter_to_batch_to_save(self)
        self.data_to_save_queue.put(self.data_to_save)
        self.data_to_save = sqlite_db.DataToSave(multi_container_images=[], single_container_images=[])
        self.byte_tracker.reset()
        self.first_line_zone = LineZone(start=Point(self.width * 3 / 4, 0), end=Point(self.width * 3 / 4, self.height), triggering_anchors=[Position.CENTER])
        self.center_line_zone = LineZone(start=Point(self.width / 2, 0), end=Point(self.width / 2, self.height), triggering_anchors=[Position.CENTER])
        self.last_line_zone = LineZone(start=Point(self.width / 4, 0), end=Point(self.width / 4, self.height), triggering_anchors=[Position.CENTER])
        self.category_counts = {
            'can': 0,
            'plastic': 0,
            'drinkbox': 0,
            'gabletop': 0,
            'pouch': 0
        }
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


def counter_to_batch_to_save(counter: Counter):
        return sqlite_db.BatchToSave(
            id=counter.current_batch_uuid,
            time_started=counter.time_batch_started,
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
            category_model=counter.category_model
        )