from typing import List
from fastapi import HTTPException, APIRouter, BackgroundTasks
from pydantic import BaseModel, Field
from prisma.enums import ImageStatus
from prisma.models import Image
from server.dependencies import db, get_settings, roboflow_project, s3_session, http_client
import uuid
import os
import io
import json
import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
from aioboto3 import Session
import aiofiles
import traceback
from time import perf_counter
from datetime import datetime

router = APIRouter(prefix="/tasks")

NUM_OF_IMAGES_PER_TASK = 20

class AssignTaskInput(BaseModel):
    num_of_tasks: int = Field(5, gt=0, le=10, description="Number of tasks to assign (maximum 10)")
    user_id: str

class CreatedTask(BaseModel):
    task_name: str
    image_count: int

class AssignTaskResponse(BaseModel):
    created_tasks: List[CreatedTask] = Field([], description="The created tasks that were uploaded to Roboflow.")

class UploadTask(BaseModel):
    task_id: str
    user_id: str
    image: Image

class PulseTask(BaseModel):
    id: str
    task_name: str
    image_count: int

class PulseCreateTaskInput(BaseModel):
    roboflow_id: str
    due_date: str
    project_id: int = 5
    company_id: int = 6
    tasks: List[PulseTask]

def extract_labels_from_image(image: Image):
    classes = [
        'can',
        'plastic',
        'drinkbox',
        'gabletop',
        'pouch',
        'container'
    ]
    categories = [{ 'id': id, 'name': class_id, 'supercategory': 'none' } for id, class_id in enumerate(classes)]
        
    annotations = []
    file_name = image.id
    images = [{ 'id': 0, 'file_name': f'{image.id}.{image.fileExtension}', 'height': image.height, 'width': image.width }]
    labels_file_name = f'{file_name}.coco.json'
    for i, bbox in enumerate(image.bboxes):
        class_id = classes.index(bbox.label)
        x1, y1, x2, y2 = bbox.x1, bbox.y1, bbox.x2, bbox.y2
        width = x2 - x1
        height = y2 - y1
        area = width * height
        annotations.append({
           'id': i,
           'image_id': 0,
           'category_id': class_id,
           'bbox':  [x1, y1, width, height],
           'area': area,
           'segmentation': [],
           'iscrowd': 0
        })

    labels_object = {
        'categories': categories,
        'images': images,
        'annotations': annotations
    }


    data = {
        'name': labels_file_name,
        'rawText': json.dumps(labels_object)
    }

    return data

async def get_s3_obj(client, s3_key):
    """send request and retrieve the obj from S3"""
    resp = await client.get_object(
        Bucket=get_settings().aws_s3_bucket,
        Key=s3_key,
    )
    obj = await resp['Body'].read()
    return obj


async def download_img(session: Session, image: Image):
    """convert the obj to image and save"""
    async with session.client('s3') as s3_client:
        obj = await get_s3_obj(s3_client, f'counti-images/{image.batchId}/{image.id}.{image.fileExtension}')
    image_path = f'{get_settings().temp_data_dir}/{image.id}.{image.fileExtension}'
    async with aiofiles.open(image_path, 'wb') as f:
        buffer = io.BytesIO(obj)
        await f.write(buffer.getbuffer())

# TODO handle failures for downloads and uploads
def upload_to_roboflow(upload_task: UploadTask):
    try:
        image_path = f'{get_settings().temp_data_dir}/{upload_task.image.id}.{upload_task.image.fileExtension}'

        labels = extract_labels_from_image(upload_task.image)

        result = roboflow_project.single_upload(
            image_path=image_path,
            annotation_path=labels,
            batch_name=f'{upload_task.user_id}: {upload_task.task_id}',
            is_prediction=True,
            num_retry_uploads=30,
        )

        os.remove(image_path)
        return result
    except Exception as e:
        print(f'Error uploading to roboflow: {e}')
        return {}

def cast_uuid_to_text(uuids: list[str]) -> str:
    output = "("
    num_of_uuids = len(uuids)
    for index, id in enumerate(uuids):
        output += f"'{id}'::uuid"
        if index != num_of_uuids - 1:
            output += ', '
        else:
            output += ')'
    return output

async def fetch_and_mark_images(num_of_images: int) -> List[str]:
    try:
        async with db.tx() as tx:
            # Step 1: Select and lock the images
            rows = await tx.query_raw(f"""
                SELECT id FROM "Image"
                WHERE "imageStatus" = '{ImageStatus.ON_QUEUE}'
                FOR UPDATE SKIP LOCKED
                LIMIT {num_of_images}
            """)
            image_ids = [row['id'] for row in rows]

            # Step 2: Update their status
            if len(image_ids) > 0:
                await tx.query_raw(f"""
                    UPDATE "Image"
                    SET "imageStatus" = '{ImageStatus.VERIFICATION_IN_PROGRESS}'
                    WHERE id IN {cast_uuid_to_text(image_ids)}
                """)

            return image_ids
    except Exception as e:
        print(f'Error fetching and marking images: ${e}')
        return []
    
async def download_and_upload_images(upload_tasks: List[UploadTask]):
    before = perf_counter()

    download_tasks = []
    for upload_task in upload_tasks:
        download_tasks.append(asyncio.create_task(download_img(s3_session, upload_task.image)))

    await asyncio.gather(*download_tasks)

    with tqdm.tqdm(desc="Upload first tasks", total=len(upload_tasks)) as pbar:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(upload_to_roboflow, arg): arg for arg in upload_tasks}
            results = []
            for future in as_completed(futures):
                results.append(future.result())
                pbar.update(1)

            images_uploaded = 0
            annotations_uploaded = 0
            for result in results:
                if result.get('image', {}).get('success', False):
                    images_uploaded += 1
                if result.get('annotation', {}).get('success', False):
                    annotations_uploaded += 1
            print(f'Roboflow upload results: {images_uploaded=}, {annotations_uploaded=}')
    
    after = perf_counter()

    print(f'Task upload took {after - before} seconds total')

    
async def handle_upload_tasks(upload_tasks: List[UploadTask]):
    first_task_upload_tasks = upload_tasks[:NUM_OF_IMAGES_PER_TASK]

    await download_and_upload_images(first_task_upload_tasks)

    if len(upload_tasks) <= NUM_OF_IMAGES_PER_TASK:
        return

    rest_upload_tasks = upload_tasks[NUM_OF_IMAGES_PER_TASK:]

    await download_and_upload_images(rest_upload_tasks)

async def create_pulse_tasks(input: PulseCreateTaskInput):
    print(f'Hitting pulse endpoint')
    response = await http_client.post('https://pulse.eazyreturn.ca/api/create-bulk-tasks', json=input.model_dump(), headers={ 'Authorization': get_settings().pulse_access_key })
    print(f'Pulse response: {response.content}')

@router.post("/", response_model=AssignTaskResponse, tags=["Tasks"])
async def assign_tasks(
    input: AssignTaskInput,
    background_tasks: BackgroundTasks
):
    try:
        # --- Execute Query ---
        num_of_images = input.num_of_tasks * NUM_OF_IMAGES_PER_TASK
        image_ids = await fetch_and_mark_images(num_of_images)
        if len(image_ids) == 0:
            raise HTTPException(status_code=500, detail=f"No more images left!")
        
        images = await db.image.find_many(
            take=input.num_of_tasks * NUM_OF_IMAGES_PER_TASK,
            order=[
                {
                    'batchId': 'asc',
                },
                {
                    'timeTaken': 'asc',
                },
                {
                    'id': 'asc'
                }
            ],
            where={ 'id': { 'in': image_ids } },
            include={ 'bboxes': True }, 
        )

        pulse_tasks_to_create: List[PulseTask] = []
        verification_sessions_to_create = []
        image_in_sessions_to_create = []

        upload_tasks: List[UploadTask] = []

        for i in range(0, len(images), NUM_OF_IMAGES_PER_TASK):
            task_id = str(uuid.uuid4())
            verification_sessions_to_create.append({
                'id': task_id,
                'userId': input.user_id
            })
            images_in_current_task = images[i:i+NUM_OF_IMAGES_PER_TASK]
            image_in_sessions_to_create.extend(list(map(lambda e: {
                'imageId': e.id,
                'verificationSessionId': task_id
            }, images_in_current_task)))

            pulse_tasks_to_create.append(PulseTask(
                id=task_id,
                task_name=f'{input.user_id}: {task_id}',
                image_count=len(images_in_current_task)
            ))

            upload_tasks.extend(list(map(lambda e: UploadTask(task_id=task_id, user_id=input.user_id, image=e), images_in_current_task)))

        await db.verificationsession.create_many(verification_sessions_to_create, skip_duplicates=True)
        await db.imageinverificationsession.create_many(image_in_sessions_to_create, skip_duplicates=True)

        if get_settings().python_env == 'PRODUCTION':
            now = datetime.now()
            await create_pulse_tasks(PulseCreateTaskInput(
                roboflow_id=input.user_id,
                due_date=f'{now.year}-{now.month:02d}-{(now.day + 1):02d}',
                tasks=pulse_tasks_to_create
            ))

        background_tasks.add_task(handle_upload_tasks, upload_tasks)

        return AssignTaskResponse(
            created_tasks=list(map(lambda e: CreatedTask(task_name=e.task_name, image_count=e.image_count), pulse_tasks_to_create))
        )
    
    except Exception as e:
        print(f"Error fetching images: {e}")
        print(traceback.format_exc())
        # Consider more specific error handling based on potential Prisma errors
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
