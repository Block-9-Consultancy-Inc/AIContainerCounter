import cv2
import sys
import os


def check_bbox_yolo_annotations(dataset_path: str, data_type: str, image_file_name: str):
    classes = ['container']

    image_path = f'{dataset_path}/{data_type}/images/{image_file_name}'
    label_file_path = f'{dataset_path}/{data_type}/labels/{image_file_name.replace('.jpg', '.txt')}'
    image = cv2.imread(image_path)
    img_height, img_width = image.shape[:2]

    labels = []

    with open(label_file_path) as f:
        label_text = f.read()
        label_text_lines = label_text.split('\n')
        for line_index, line in enumerate(label_text_lines):
            if line == '':
                continue
            line_items = line.split(' ')
            label, center_x, center_y, width, height,  = (classes[int(line_items[0])], round(float(line_items[1]) * img_width), round(float(line_items[2]) * img_height), round(float(line_items[3]) * img_width), round(float(line_items[4]) * img_height))
            xyxy_format = (label, center_x - round(width / 2), center_y - round(height / 2), center_x + round(width / 2), center_y + round(height / 2))
            labels.append(xyxy_format)

    for label in labels:
        image = cv2.rectangle(image, (label[1], label[2]), (label[3], label[4]), (255, 255, 255), 2, cv2.LINE_AA)
        image = cv2.putText(image, label[0], (label[1], label[2] - 10), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 1, cv2.LINE_AA)

    os.makedirs('test-bbox-images', exist_ok=True)
    cv2.imwrite(f'test-bbox-images/{image_file_name}', image)

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('Missing arguments! Usage: [dataset path] [data type] [image file name]')

    dataset_path = sys.argv[1]
    data_type = sys.argv[2]
    image_file_name = sys.argv[3]

    check_bbox_yolo_annotations(dataset_path, data_type, image_file_name)