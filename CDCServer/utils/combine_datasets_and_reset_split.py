import json
import os
import random
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import tqdm
import yaml
import time

with open('image_id_to_chunks.json') as f:
    image_id_to_chunk_id: dict[str, str] = json.load(f)

def combine_datasets_and_reset_split(src_dir: str, dest_dir: str):
    datasets = os.listdir(src_dir)
    os.makedirs(f'{dest_dir}/train/images', exist_ok=True)
    os.makedirs(f'{dest_dir}/train/labels', exist_ok=True)
    os.makedirs(f'{dest_dir}/valid/images', exist_ok=True)
    os.makedirs(f'{dest_dir}/valid/labels', exist_ok=True)
    os.makedirs(f'{dest_dir}/test/images', exist_ok=True)
    os.makedirs(f'{dest_dir}/test/labels', exist_ok=True)

    jobs = []
    for dataset in datasets:
        for split in ['train', 'valid', 'test']:
            if not os.path.exists(f'{src_dir}/{dataset}/{split}'):
                continue
            for image in os.listdir(f'{src_dir}/{dataset}/{split}/images'):
                chunk_id, new_split = get_new_split(image)
                jobs.append([f'{src_dir}/{dataset}', split, new_split, image, dest_dir])

    print(f'Total images found: {len(jobs)}')

    with tqdm.tqdm(total=len(jobs), desc=f'Combining and resetting split') as pbar:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(handle_image, *arg): arg for arg in jobs}
            for _ in as_completed(futures):
                pbar.update(1)

    train_amount= len(os.listdir(f'{dest_dir}/train/images'))
    valid_amount = len(os.listdir(f'{dest_dir}/valid/images'))
    test_amount = len(os.listdir(f'{dest_dir}/test/images'))
    total = train_amount + valid_amount + test_amount
    split_ratio = f'{(train_amount / total * 100):0.2f}:{(valid_amount / total * 100):0.2f}:{(test_amount / total * 100):0.2f}'

    new_yaml = {
        'train': f'{dest_dir}/train/images',
        'val': f'{dest_dir}/valid/images',
        'test': f'{dest_dir}/test/images',
        'splits': {
            'train_amount': train_amount,
            'valid_amount': valid_amount,
            'test_amount': test_amount,
            'total_amount': total,
            'split_ratio': split_ratio
        }
    }

    with open(f'{dest_dir}/data.yaml', 'w') as f:
        yaml.dump(new_yaml, f)


def chunk_id_to_split(chunk_id: str, seed='42'):
    random.seed(f'{chunk_id}:{seed}')
    values = ['train', 'valid', 'test']

    probabilities = [0.7, 0.2, 0.1]
    return random.choices(values, weights=probabilities, k=1)[0]


def roboflow_image_file_name_to_id(roboflow_image_file_name: str):
    if 'prefix' in roboflow_image_file_name:
        return roboflow_image_file_name.split('_')[3].removesuffix('.jpg')
    underscore_count = roboflow_image_file_name.count('_')
    match underscore_count:
        case 0:
            split_index = 0
        case 1:
            split_index = 0
        case 2:
            split_index = 0
        case _:
            split_index = 1
    return roboflow_image_file_name.split('_')[split_index]

def get_new_split(image_file_name: str):
    image_id = roboflow_image_file_name_to_id(image_file_name)
    chunk_id = image_id_to_chunk_id.get(image_id)
    return chunk_id, chunk_id_to_split(chunk_id)

def handle_image(dataset_path: str, old_split: str, new_split: str, image_file_name: str, dest_dir: str):
    label_file_name = image_file_name.replace('.jpg', '.txt')
    shutil.copy(f'{dataset_path}/{old_split}/images/{image_file_name}', f'{dest_dir}/{new_split}/images/{image_file_name}')
    shutil.copy(f'{dataset_path}/{old_split}/labels/{label_file_name}', f'{dest_dir}/{new_split}/labels/{label_file_name}')


if __name__ == '__main__':
    combine_datasets_and_reset_split('/workspace/CDCServer/resources/all-datasets', '/workspace/CDCServer/resources/full-dataset')