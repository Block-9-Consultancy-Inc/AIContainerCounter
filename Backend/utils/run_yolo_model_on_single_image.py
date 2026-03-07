from ultralytics import YOLO
from supervision import BoxAnnotator, LabelAnnotator, Detections
import cv2
import sys
import os


def run_model_on_single_image(img_path: str):
    box_annotator = BoxAnnotator()
    label_annotator = LabelAnnotator()

    model = YOLO('counti-auto-annotator.pt')

    img = cv2.imread(img_path)
    img = cv2.copyMakeBorder(img, 50, 50, 50, 50, cv2.BORDER_CONSTANT)
    result = model.predict(img.copy(), imgsz=1440, nms=True, conf=0.5)[0]

    detections = Detections.from_ultralytics(result)

    labels = [f'{detections.confidence[index]:0.2f} {model.names[class_id]}' for index, class_id in enumerate(detections.class_id)]
    annotated_bbox_image = box_annotator.annotate(img.copy(), detections)
    annotated_bbox_image = label_annotator.annotate(annotated_bbox_image, detections, labels)

    os.makedirs('test-predictions', exist_ok=True)

    img_file_name = img_path.split('/')[-1]

    cv2.imwrite(f'test-predictions/{img_file_name}', annotated_bbox_image)

if __name__ == '__main__':
    img_path = sys.argv[1]

    run_model_on_single_image(img_path)