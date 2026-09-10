import os
from sqlmodel_db import init_db, Batch
from random import randint
import shutil

init_db()

os.makedirs('yolo/train/images', exist_ok=True)
os.makedirs('yolo/valid/images', exist_ok=True)
os.makedirs('yolo/test/images', exist_ok=True)
os.makedirs('yolo/train/labels', exist_ok=True)
os.makedirs('yolo/valid/labels', exist_ok=True)
os.makedirs('yolo/test/labels', exist_ok=True)


batch_info = Batch.select(Batch.id, Batch.count)

for batch in batch_info:
    print(f'working on batch {batch.id}')
    data_type_identifier = randint(0, 99)
    data_type = None
    if data_type_identifier >= 0 and data_type_identifier < 70:
        data_type = 'train'
    elif data_type_identifier >= 70 and data_type_identifier < 90:
        data_type = 'valid'
    elif data_type_identifier >= 90 and data_type_identifier < 100:
        data_type = 'test'
    for image in batch.multiContainerImages:
        print(f'working on image {image.id}')
        shutil.copyfile(f'images/{batch.id}/multi_container_images/{image.id}.{image.index}.jpg', f'yolo/{data_type}/images/{batch.id}_{image.id}.{image.index}.jpg')
        with open(f'yolo/{data_type}/labels/{batch.id}_{image.id}.{image.index}.txt', 'w') as f:
            for bbox in image.bboxes:
                x1, y1, x2, y2 = bbox.x1, bbox.y1, bbox.x2, bbox.y2
                height = y2 - y1
                width = x2 - x1
                center_x = x1 + width / 2
                center_y = y1 + height / 2
                norm_center_x, norm_center_y, norm_width, norm_height = center_x / image.width, center_y / image.height, width / image.width, height / image.height
                f.write(f'0 {norm_center_x} {norm_center_y} {norm_width} {norm_height}\n')


# train_amount, valid_amount, test_amount = len(os.listdir(f'yolo/train/images')), len(os.listdir(f'yolo/valid/images')), len(os.listdir(f'yolo/test/images'))
# print(f'{train_amount=}, {valid_amount=}, {test_amount=}')