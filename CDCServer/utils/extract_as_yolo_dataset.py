import cv2
import random
import os
from server.routers.bbox_correction import apply_corrections, model_to_correction
from prisma import Client
from prisma.models import Image
from prisma.enums import ImageStatus, BatchType
import traceback
import tqdm
import asyncio

classes = [
    'can',
    'plastic',
    'drinkbox',
    'gabletop',
    'pouch'
]

number_of_bboxes_skipped = 0

def convert_image_to_yolo_format(image: Image):
    global number_of_bboxes_skipped
    before_bboxes = list(map(lambda e: { 'uuid': e.id, 'x': e.x1, 'y': e.y1, 'w': e.x2 - e.x1, 'h': e.y2 - e.y1, 'label': e.label }, image.bboxes))
    image.imageInVerificationSession.sort(key=lambda e: e.verificationSession.timeAssigned.timestamp())
    prev_bboxes = before_bboxes
    for imageInVerificationSession in image.imageInVerificationSession:
        current_bboxes = apply_corrections(prev_bboxes, list(map(lambda e: model_to_correction(e), imageInVerificationSession.corrections)))
        prev_bboxes = current_bboxes
        after_bboxes = current_bboxes

    output = ''

    for bbox in after_bboxes:
        if bbox.get('x') is None or bbox.get('y') is None or bbox.get('w') is None or bbox.get('h') is None:
            continue
        class_label = 0 if bbox.get('label') not in classes else classes.index(bbox.get('label'))
        center_x = max(min(bbox.get('x') + int(bbox.get('w') / 2), image.width), 0)
        center_y = max(min(bbox.get('y') + int(bbox.get('h') / 2), image.height), 0)
        width = min(image.width - bbox.get('x'), max(0, bbox.get('w')))
        height = min(image.height - bbox.get('y'), max(0, bbox.get('h')))
        if width < 3 or height < 3:
            number_of_bboxes_skipped += 1
            continue
        line = f'{class_label} {(center_x / image.width):.4f} {(center_y / image.height):.4f} {(width / image.width):.4f} {(height / image.height):.4f}\n'
        output += line

    return output

def check_bbox_yolo_annotations(image_id: str, yolo_format_text: str):
    image = cv2.imread(f'resources/densifier_images/{image_id}.jpg')
    img_height, img_width = image.shape[:2]

    labels = []

    for line_index, line in enumerate(yolo_format_text.split('\n')):
        if line == '':
            continue
        line_items = line.split(' ')
        label, center_x, center_y, width, height,  = (classes[int(line_items[0])], round(float(line_items[1]) * img_width), round(float(line_items[2]) * img_height), round(float(line_items[3]) * img_width), round(float(line_items[4]) * img_height))
        xyxy_format = (label, center_x - round(width / 2), center_y - round(height / 2), center_x + round(width / 2), center_y + round(height / 2))
        labels.append(xyxy_format)

    for label in labels:
        image = cv2.rectangle(image, (label[1], label[2]), (label[3], label[4]), (255, 255, 255), 2, cv2.LINE_AA)
        image = cv2.putText(image, label[0], (label[1], label[2] - 10), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 1, cv2.LINE_AA)

    os.makedirs('resources/test-bbox-images', exist_ok=True)
    cv2.imwrite(f'resources/test-bbox-images/{image_id}.jpg', image)

async def yolo_format():
    db = Client(
        http={
            'timeout': 300
        }
    )
    await db.connect()

    try:
        images = await db.image.find_many(
            where={ 'AND':  [
                { 'imageStatus': ImageStatus.VERIFIED },
                { 'batch': { 'is': {
                    'batchType': BatchType.DENSIFIER
                }}}
            ]},
            include={
                'bboxes': True,
                'imageInVerificationSession': { 
                    'include': {
                        'corrections': True,
                        'verificationSession': True
                    }
                }
            },
        )

        for image in tqdm.tqdm(images, desc="Calculating and extracting yolo annotations"):
            yolo_format_text = convert_image_to_yolo_format(image)
            with open(f'resources/densifier_image_annotations/{image.id}.txt', 'w') as f:
                f.write(yolo_format_text)
        print(f'Number of small bboxes skipped: {number_of_bboxes_skipped}')
    except Exception as e:
        print(f"Error occurred: {e}")
        traceback.print_exc()
    finally:
        await db.disconnect()

import random
import shutil
import yaml

async def get_images_to_ignore(db: Client):
    results = await db.query_raw("""
            select distinct i.id
            from "Image" i 
                left join "Batch" b on b.id = i."batchId" 
                left join "ImageInVerificationSession" ivs on i.id = ivs."imageId"
                left join "VerificationSession" vs on vs.id = ivs."verificationSessionId" 
            where b."batchType" = 'DENSIFIER' and i."imageStatus" = 'VERIFIED' and (vs."userId" in ($1, $2, $3) or vs.id = $4::uuid);
        """, "FK250627", "TH250627", "YH250627", "22f066c5-eb91-44ed-aff9-8c34df021396")

    return list(map(lambda e: e.get('id'), results))

def chunk_id_to_split(chunk_id: str, seed='42'):
    random.seed(f'{chunk_id}:{seed}')
    values = ['train', 'valid', 'test']

    probabilities = [0.7, 0.2, 0.1]
    return random.choices(values, weights=probabilities, k=1)[0]


async def setup_yolo_dataset():
    db = Client(
        http={
            'timeout': 300
        }
    )
    await db.connect()

    os.makedirs('resources/densifier_dataset/train/images', exist_ok=True)
    os.makedirs('resources/densifier_dataset/train/labels', exist_ok=True)
    os.makedirs('resources/densifier_dataset/valid/images', exist_ok=True)
    os.makedirs('resources/densifier_dataset/valid/labels', exist_ok=True)
    os.makedirs('resources/densifier_dataset/test/images', exist_ok=True)
    os.makedirs('resources/densifier_dataset/test/labels', exist_ok=True)

    images_to_ignore = await get_images_to_ignore(db)

    print(f'num images to ignore: {len(images_to_ignore)}')

    try:
        images = await db.image.find_many(
            where={ 'AND':  [
                { 'id': { 'not': { 'in': images_to_ignore }}},
                { 'imageStatus': ImageStatus.VERIFIED },
                { 'batch': { 'is': {
                    'batchType': BatchType.DENSIFIER
                }}}
            ]},
        )

        counts = {
            'train': 0,
            'valid': 0,
            'test': 0
        }

        for image in tqdm.tqdm(images, desc="Calculating and extracting yolo annotations"):
            split = chunk_id_to_split(image.chunkId)
            shutil.copy(f'resources/densifier_images/{image.id}.jpg', f'resources/densifier_dataset/{split}/images/{image.id}.jpg')
            shutil.copy(f'resources/densifier_image_annotations/{image.id}.txt', f'resources/densifier_dataset/{split}/labels/{image.id}.txt')
            counts[split] += 1

        total = counts.get('train') + counts.get('valid') + counts.get('test')
        split_ratio = f'{(counts.get('train') / total * 100):0.2f}:{(counts.get('valid') / total * 100):0.2f}:{(counts.get('test') / total * 100):0.2f}'

        new_yaml = {
            'train': f'resources/densifier_dataset/train/images',
            'val': f'resources/densifier_dataset/valid/images',
            'test': f'resources/densifier_dataset/test/images',
            'splits': {
                'train_amount': counts.get('train'),
                'valid_amount': counts.get('valid'),
                'test_amount': counts.get('test'),
                'total_amount': total,
                'split_ratio': split_ratio
            }
        }

        with open(f'resources/densifier_dataset/data.yaml', 'w') as f:
            yaml.dump(new_yaml, f)
    except Exception as e:
        print(f"Error occurred: {e}")
        traceback.print_exc()
    finally:
        await db.disconnect()

if __name__ == '__main__':
    asyncio.run(yolo_format())