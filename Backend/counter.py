from supervision import TraceAnnotator, BoundingBoxAnnotator, LabelAnnotator, Detections, ByteTrack, LineZoneAnnotator, LineZone, Point, Position
from utils.category_classifier import CategoryClassifier
from datetime import datetime
import numpy as np
import traceback

category_classes = [
    'can',
    'plastic',
    'drinkbox',
    'gabletop',
    'pouch'
]

class Counter:
    def __init__(self, names: list[str], width: int, height: int):
        self.width = width
        self.height = height
        self.names = names
        self.byte_tracker = ByteTrack()
        self.line_zone = LineZone(start=Point(self.width / 2, 0), end=Point(self.width / 2, self.height))
        self.line_zone_annotator = LineZoneAnnotator(text_scale=1, thickness=2, text_thickness=2)
        self.box_annotator = BoundingBoxAnnotator(thickness=2)
        self.trace_annotator = TraceAnnotator(thickness=2)
        self.label_annotator = LabelAnnotator(text_thickness=2, text_scale=1)
        self.category_classifier = CategoryClassifier('resnet_v1_18_unscaled.pth')
        self.tracker_id_to_category = {}
        self.category_counts = {
            'can': 0,
            'plastic': 0,
            'drinkbox': 0,
            'gabletop': 0,
            'pouch': 0
        }
        self.expected_category_counts: dict[str, int] = None
        self.time_batch_started = datetime.now()

    def trigger(self, decoded_frame: np.ndarray, detections: Detections):
        detections = self.byte_tracker.update_with_detections(detections)

        annotated_frame = self.trace_annotator.annotate(
            scene=decoded_frame.copy(),
            detections=detections)
        annotated_frame = self.box_annotator.annotate(
            scene=annotated_frame,
            detections=detections)
        

        center_crossed_in, center_crossed_out = self.line_zone.trigger(detections)
        annotated_frame = self.line_zone_annotator.annotate(annotated_frame, line_counter=self.line_zone)

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
            return annotated_frame, self.line_zone.in_count, self.line_zone.out_count

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

            return annotated_frame, self.line_zone.in_count, self.line_zone.out_count
        except Exception as e:
            print(f'got error in counter trigger: {e}')
            error_traceback = traceback.format_exc()
            print(error_traceback)
    
    def reset_counter(self):
        self.byte_tracker.reset()
        self.line_zone = LineZone(start=Point(self.width / 2, 0), end=Point(self.width / 2, self.height))
        self.category_counts = {
            'can': 0,
            'plastic': 0,
            'drinkbox': 0,
            'gabletop': 0,
            'pouch': 0
        }
        self.tracker_id_to_category = {}
        self.time_batch_started = datetime.now()

    def set_expected_count(self, expected_category_counts: dict[str, int]):
        self.expected_category_counts = expected_category_counts