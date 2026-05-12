import os
import supervision as sv
import json
import numpy as np
import roboflow
from sqlite_db import get_all_batches_from_day, MultiContainerImage, SingleContainerImage, BBox, Batch
from datetime import datetime, timedelta
from random import randint
from concurrent.futures import ThreadPoolExecutor, as_completed
import tqdm
import traceback

SRC_DIR = '/home/counti/Projects/AIContainerCounter/Backend/images'

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)
    

failed_uploads = {}
already_uploaded = {}


def create_labels_from_detections(image_width, image_height, image_file_name: str, detections: sv.Detections):
    classes = [
        'can',
        'plastic',
        'drinkbox',
        'gabletop',
        'pouch',
        'container'
    ]
    categories = [{ 'id': int(id), 'name': class_id, 'supercategory': 'none '} for id, class_id in enumerate(classes)]
        
    annotations = []
    file_name = image_file_name.split('.jpg')[0]
    images = [{ 'id': 0, 'file_name': image_file_name, 'height': image_height, 'width': image_width }]
    labels_file_name = f'{file_name}.coco.json'
    for i in range(0, len(detections.class_id)):
        class_id = detections.class_id[i]
        x1, y1, x2, y2 = detections.xyxy[i].astype(int)
        width = x2 - x1
        height = y2 - y1
        area = width * height
        if (x1 <= (image_width * 0.025) or abs(image_width - x2) <= (image_width * 0.025)) and width < (image_width * 0.075):
            continue
        annotations.append({
           'id': int(i),
           'image_id': 0,
           'category_id': int(class_id),
           'bbox':  [int(x1), int(y1), int(width), int(height)],
           'area': int(area),
           'segmentation': [],
           'iscrowd': 0
        })
    labels_object = {
        'categories': categories,
        'images': images,
        'annotations': annotations
    }
    
    return {
        'name': labels_file_name,
        'rawText': json.dumps(labels_object)
    }

def extract_args_for_batch(batch: Batch, upload_batch_name: str, tags: list[str]):

    args = []

    single_container_images = list(batch.singleContainerImages)

    for multi_container_image in batch.multiContainerImages:
        detections = multi_container_image_to_detections(multi_container_image, single_container_images)
        image_path = f'{SRC_DIR}/{multi_container_image.batch_id}/multi_container_images/{multi_container_image.id}.{multi_container_image.index}.jpg'
        annotations_path = create_labels_from_detections(multi_container_image.width, multi_container_image.height, f'{multi_container_image.id}.jpg', detections)
        args.append((tags, upload_batch_name, image_path, annotations_path))

    return args

def upload_image_and_label(roboflow_project: roboflow.Project, tags: list[str], upload_batch_name: str, image_path: str, annotations_path: dict):
    try:
        roboflow_project.single_upload(image_path=image_path,
            annotation_path=annotations_path,
            tag_names=tags,
            batch_name=upload_batch_name,
            is_prediction=True,
            num_retry_uploads=3,
        )
    except Exception as e:
        print(f'Error: {e}')
        print(traceback.format_exc())
        with open(f'{SRC_DIR}/failed_uploads.txt', 'a') as f:
            f.write(f'{image_path}\n')


def multi_container_image_to_detections(multi_container_image: MultiContainerImage, single_container_images: list[SingleContainerImage]):
    bboxes: list[BBox] = list(multi_container_image.bboxes)

    xyxy = []
    class_id = []
    tracker_id = []

    categories = [
        'can',
        'plastic',
        'drinkbox',
        'gabletop',
        'pouch',
        'container'
    ]

    for bbox in bboxes:
        xyxy.append([bbox.x1, bbox.y1, bbox.x2, bbox.y2])
        tracker_id.append(bbox.tracker_id)
        matching_single_container_images = list(filter(lambda e: e.tracker_id == bbox.tracker_id, single_container_images))
        if len(matching_single_container_images) > 0:
            class_id.append(categories.index(matching_single_container_images[0].predicted_category))
        else:
            class_id.append(categories.index('container'))



    return sv.Detections(
        xyxy=np.array(xyxy),
        class_id=np.array(class_id),
        tracker_id=np.array(tracker_id)
    )


def print_images_per_day():
    now = datetime.now()
    today = datetime(now.year, now.month, now.day)


    for i in range(-2, 10):
        current_day = today - timedelta(days=i)
        total_images = 0
        batches_from_day = get_all_batches_from_day(current_day)
        for batch in batches_from_day:
            total_images += len(list(batch.multiContainerImages))
        print(f'total images on day ${current_day}: {total_images}')

if __name__ == '__main__':
    rf = roboflow.Roboflow(api_key="x1PzlcDfIXDRS53dfvY9")

    workspace = rf.workspace('visiontest-95q12')

    project = workspace.project('ai-counting-machine')
    os.makedirs(f'{SRC_DIR}/annotation_files', exist_ok=True)
    
    now = datetime.now()
    today = datetime(now.year, now.month, now.day)

    batches_with_data_missing = []
    data_to_upload = []

    total_images = 0
    for i in range(0, 6):
        current_day = today - timedelta(days=i)
        batches_from_day = get_all_batches_from_day(current_day)
        num_of_images = 0
        num_of_batches = 0
        for batch in batches_from_day:
            images = list(batch.multiContainerImages)
            num_of_images += len(images)
            num_of_batches += 1
            print(f'{batch.time_started} - {batch.id}:{len(images)} {batch.count}:{batch.expected_count}')
            if os.path.isdir(f'{SRC_DIR}/{batch.id}'):
                data_to_upload.extend(extract_args_for_batch(batch, f'{current_day.year}-{current_day.month:02}-{current_day.day:02}', ['sapperton', f'{current_day.year}-{current_day.month:02}-{current_day.day:02}']))
            else:
                batches_with_data_missing.append(str(batch.id))
                with open(f'{SRC_DIR}/batches_missing_data.json', 'w') as f:
                    json.dump(batches_with_data_missing, f, indent=4)
        total_images += num_of_images
        print(f'{current_day}: {num_of_images=}, {num_of_batches=}')
    print(f'total images: {total_images}')

    with tqdm.tqdm(desc="Uploading images to Roboflow", total=len(data_to_upload)) as pbar:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(upload_image_and_label, project, *arg): arg for arg in data_to_upload}
            for future in as_completed(futures):
                pbar.update(1)