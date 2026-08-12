from typing import List, Tuple, Dict, Optional
from fastapi import HTTPException, APIRouter, BackgroundTasks, status
from pydantic import BaseModel, Field
from prisma.enums import ImageStatus
from prisma.models import Image, VerificationSession
from server.dependencies import db, get_settings, s3_session, http_client
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
from datetime import datetime, timezone
from server.routers.bbox_correction import calculate_corrections, correction_to_model, generate_image_with_bounding_boxes, apply_corrections



router = APIRouter(prefix="/tasks")

NUM_OF_IMAGES_PER_TASK = 20

class AssignTaskInput(BaseModel):
    user_id: str

class CreatedTask(BaseModel):
    task_name: str
    image_count: int

class AssignTaskResponse(BaseModel):
    task: CreatedTask = Field(..., description="The task that was created.")
    images: List[Image] = Field([], description="The images that were assigned to the tasks.")
class GetActiveTaskResponse(BaseModel):
    task: Optional[CreatedTask] = Field(None, description="The active task that is currently assigned to the user.") # CreatedTask is used here to keep consistency with the AssignTaskResponse
    images: List[Image] = Field([], description="The images that are part of the active task.")

class CompleteTaskInput(BaseModel):
    images_ids: List[str] = Field(..., description="The IDs of the images that were verified in the task.")
class ExistingTasksInput(BaseModel):
    take: int = Field(5, gt=0, le=50, description="Page size")
    cursor: List[str] = Field([], description="The IDs of the verification sessions already seen.")
    user_id: str = Field(..., description='The User ID')

class ExistingTasksResponse(BaseModel):
    tasks: List[VerificationSession] = Field([], description="The existing verification sessions based on the filters supplied")

class UploadTask(BaseModel):
    task_id: str
    user_id: str
    image_prefix: str
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

class BBoxCoordinates(BaseModel):
    x1: float = Field(..., description="Left coordinate of the bounding box")
    y1: float = Field(..., description="Top coordinate of the bounding box")
    x2: float = Field(..., description="Right coordinate of the bounding box")
    y2: float = Field(..., description="Bottom coordinate of the bounding box")


class UpdatedBBox(BaseModel):
    label: str = Field(...,
                       description="The updated label for the bounding box")
    time: float = Field(0, description="Time marker for the bounding box")
    coordinates: BBoxCoordinates = Field(...,
                                         description="The coordinates of the bounding box")

class UpdatedImage(BaseModel):
    image_id: str = Field(..., description="Image ID of image.")
    updated_bboxes: List[UpdatedBBox] = Field(..., description="The updated bboxes of the image.")

class CompleteTaskBboxInput(BaseModel):
    user_id: str = Field(...,
                         description="The ID of the user completing the task")
    images: List[UpdatedImage] = Field(
        ..., description="The updated images with its bounding boxes with their new coordinates and labels")

class GetActiveTaskInput(BaseModel):
    user_id: str = Field(..., description='The User ID')

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


async def download_img_for_upload_task(session: Session, upload_task: UploadTask):
    """convert the obj to image and save"""
    image = upload_task.image
    async with session.client('s3') as s3_client:
        obj = await get_s3_obj(s3_client, f'counti-images/{image.batchId}/{image.id}.{image.fileExtension}')
    image_path = f'{get_settings().temp_data_dir}/{upload_task.image_prefix}_{image.id}.{image.fileExtension}'
    async with aiofiles.open(image_path, 'wb') as f:
        buffer = io.BytesIO(obj)
        await f.write(buffer.getbuffer())

async def download_img(session: Session, image: Image):
    """convert the obj to image and save"""
    async with session.client('s3') as s3_client:
        obj = await get_s3_obj(s3_client, f'counti-images/{image.batchId}/{image.id}.{image.fileExtension}')
    image_path = f'{get_settings().temp_data_dir}/{image.id}.{image.fileExtension}'
    async with aiofiles.open(image_path, 'wb') as f:
        buffer = io.BytesIO(obj)
        await f.write(buffer.getbuffer())
    return image_path

# TODO handle failures for downloads and uploads
def upload_to_roboflow(upload_task: UploadTask):
    try:
        image_path = f'{get_settings().temp_data_dir}/{upload_task.image_prefix}_{upload_task.image.id}.{upload_task.image.fileExtension}'

        labels = extract_labels_from_image(upload_task.image)

        # result = roboflow_project.single_upload(
        #     image_path=image_path,
        #     annotation_path=labels,
        #     batch_name=f'{upload_task.user_id}: {upload_task.task_id}',
        #     is_prediction=True,
        #     num_retry_uploads=30,
        # )

        os.remove(image_path)
        # return result
        return None
    except Exception as e:
        print(f'Error uploading to roboflow: {e}')
        print(traceback.format_exc())
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

async def fetch_and_mark_images(num_of_images: int) -> Tuple[List[str], List[Dict[str, str]]]:
    try:
        async with db.tx() as tx:
            # Step 1: Select and lock the images
            rows = await tx.query_raw(f"""
                SELECT i.id, i."batchId", i.index FROM "Image" i
                INNER JOIN "Batch" b ON b.id = i."batchId"
                WHERE "imageStatus" = '{ImageStatus.ON_QUEUE}'
                ORDER BY b."timeSubmitted" DESC, i."batchId", i."index" ASC
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

            return image_ids, rows
    except Exception as e:
        print(f'Error fetching and marking images: ${e}')
        return [], []
    
async def download_and_upload_images(upload_tasks: List[UploadTask]):
    before = perf_counter()

    download_tasks = []
    for upload_task in upload_tasks:
        download_tasks.append(asyncio.create_task(download_img_for_upload_task(s3_session, upload_task)))

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
    response = await http_client.post('https://pulse.eazyreturn.ca/api/create-bulk-tasks', json=input.model_dump(), headers={ 'Authorization': get_settings().pulse_access_key }, follow_redirects=True)
    print(f'Pulse response: {response.content}')

@router.post("/", response_model=AssignTaskResponse, tags=["Tasks"])
async def assign_tasks(input: AssignTaskInput):
    try:
        last_session = await db.verificationsession.find_first(where={ 'userId': input.user_id }, order=[{ 'timeAssigned': 'desc' }])

        if last_session is not None:
            seconds_since_last_assignment = (datetime.now(timezone.utc) - last_session.timeAssigned).total_seconds()
            if seconds_since_last_assignment < 10:
                raise HTTPException(status_code=400, detail=f"Need to wait 10 seconds, only {seconds_since_last_assignment} passed")
            
        # --- Execute Query ---
        num_of_images = NUM_OF_IMAGES_PER_TASK
        image_ids, image_info = await fetch_and_mark_images(num_of_images)
        batches = list(set([image['batchId'] for image in image_info]))

        image_prefix_map = {}
        for image in image_info:
            image_id = image['id']
            image_index = image['index']
            batch_index = batches.index(image['batchId'])
            image_prefix_map[image_id] = f'prefix_{batch_index:05d}_{image_index:05d}'

        if len(image_ids) == 0:
            raise HTTPException(status_code=500, detail=f"No more images left!")
        
        images_map = {image.id: image for image in (await db.image.find_many(
            take=input.num_of_tasks * NUM_OF_IMAGES_PER_TASK,
            where={ 'id': { 'in': image_ids } },
            include={ 'bboxes': True }, 
        ))}

        images: List[Image] = []
        for image_id in image_ids:
            images.append(images_map[image_id])

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

            upload_tasks.extend(list(map(lambda e: UploadTask(task_id=task_id, user_id=input.user_id, image=e, image_prefix=image_prefix_map[e.id]), images_in_current_task)))

        await db.verificationsession.create_many(verification_sessions_to_create, skip_duplicates=True)
        await db.imageinverificationsession.create_many(image_in_sessions_to_create, skip_duplicates=True)

        if get_settings().python_env == 'PRODUCTION':
            now = datetime.now()
            await create_pulse_tasks(PulseCreateTaskInput(
                roboflow_id=input.user_id,
                due_date=f'{now.year}-{now.month:02d}-{(now.day + 1):02d}',
                tasks=pulse_tasks_to_create
            ))

        return AssignTaskResponse(
            created_tasks=CreatedTask(task_name=pulse_tasks_to_create[0].task_name, image_count=NUM_OF_IMAGES_PER_TASK),
            images = list(images_map.values())
        )
    
    except Exception as e:
        print(f"Error fetching images: {e}")
        print(traceback.format_exc())
        # Consider more specific error handling based on potential Prisma errors
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.post("/get-active-task", response_model=GetActiveTaskResponse, tags=["Tasks"])
async def get_active_task(
    input: GetActiveTaskInput,
):
    verification_session = await db.verificationsession.find_first(
        where={
            'userId': input.user_id,
            'timeCompleted': None
        },
        order={
            'timeAssigned': 'desc'
        },
        include={
            'imageInVerificationSession': { 'include': { 'image': { 'include': { 'bboxes': True }}}}
        }
    )

    if verification_session is None:
        return GetActiveTaskResponse(
            active_task=None,
            images=[]
        )

    active_task = CreatedTask(
        task_name=verification_session.id,
        image_count=len(verification_session.imageInVerificationSession)
    )

    return GetActiveTaskResponse(
        active_task=active_task,
        images=[image.image for image in verification_session.imageInVerificationSession]
    )


@router.post("/existing", response_model=ExistingTasksResponse, tags=["Tasks"])
async def get_existing_tasks(
    input: ExistingTasksInput
):
    verification_sessions = await db.verificationsession.find_many(
        take=input.take,
        where={
            'id': { 'not_in': input.cursor },
            'userId': input.user_id
        },
        order={
            'timeAssigned': 'desc'
        },
        include={
            'imageInVerificationSession': { 'include': { 'image': { 'include': { 'bboxes': True }}}}
        }
    )

    return ExistingTasksResponse(tasks=verification_sessions)


@router.post(
    "/complete-task",
    status_code=status.HTTP_200_OK,
    summary="Complete a verification task by processing bbox corrections",
    tags=["Tasks"]
)
async def complete_task(input_data: CompleteTaskBboxInput):
    """
    Completes a verification task by:
    1. Finding the user's active verification session
    2. Updating bounding boxes with new coordinates and labels
    3. Setting images in session to VERIFIED
    4. Setting completion date on verification session

    Returns a summary of the updates made.
    """
    try:
        # Get active verification session for user
        verification_session = await db.verificationsession.find_first(
            where={
                'userId': input_data.user_id,
                'timeCompleted': None
            },
            include={
                'imageInVerificationSession': True
            }
        )

        if not verification_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active verification session found for user {input_data.user_id}"
            )
        
        image_ids = list(map(lambda e: e.image_id, input_data.images))
        
        original_images = await db.image.find_many(
            where={ 'id': { 'in': image_ids }},
            include={
                'bboxes': True
            }
        )

        original_images_map = {image.id: image for image in original_images}

        # os.makedirs(f'{get_settings().temp_data_dir}/{verification_session.userId}-{verification_session.id}', exist_ok=True)
        all_corrections = []
        for index, image in enumerate(input_data.images):
            # Calculate corrections and insert into corrections table
            original_bboxes = original_images_map.get(image.image_id).bboxes

            before_bboxes = list(map(lambda orig: {'uuid': orig.id, 'x': orig.x1, 'y': orig.y1,
                        'w': orig.x2 - orig.x1, 'h': orig.y2 - orig.y1, 'label': orig.label}, original_bboxes))
            after_bboxes = list(map(lambda updated_bbox: {'x': updated_bbox.coordinates.x1, 'y': updated_bbox.coordinates.y1, 'w': updated_bbox.coordinates.x2 -
                        updated_bbox.coordinates.x1, 'h': updated_bbox.coordinates.y2 - updated_bbox.coordinates.y1, 'label': updated_bbox.label} , image.updated_bboxes))
            og_corrections = calculate_corrections(before_bboxes, after_bboxes)
            corrections = list(map(lambda e: correction_to_model(image.image_id, e, verification_session.id), og_corrections))
            all_corrections.extend(corrections)

            # print(f'index: {index}, corrections: {og_corrections}')
            # image_path = await download_img(s3_session, original_images_map.get(image.image_id))
            # generate_image_with_bounding_boxes(before_bboxes, image_path, f'{get_settings().temp_data_dir}/{verification_session.userId}-{verification_session.id}/{index}-{image.image_id}-before.jpg')
            # generate_image_with_bounding_boxes(after_bboxes, image_path, f'{get_settings().temp_data_dir}/{verification_session.userId}-{verification_session.id}/{index}-{image.image_id}-after-direct.jpg')
            # after_bboxes_applied = apply_corrections(before_bboxes, og_corrections)
            # generate_image_with_bounding_boxes(after_bboxes_applied, image_path, f'{get_settings().temp_data_dir}/{verification_session.userId}-{verification_session.id}/{index}-{image.image_id}-after.jpg')

        if all_corrections:
            await db.correction.create_many(data=all_corrections, skip_duplicates=True)

        # Update all images in session to VERIFIED
        images_updated = await db.image.update_many(
            data={'imageStatus': ImageStatus.VERIFIED},
            where={'id': {'in': image_ids}}
        )

        # Set completion date on verification session
        await db.verificationsession.update(
            where={'id': verification_session.id},
            data={'timeCompleted': datetime.now()}
        )

        return {
            "corrections_created": len(all_corrections),
            'images_updated': images_updated,
            "session_completed": verification_session.id
        }
    except Exception as e:
        print(f"Error completing task: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not complete task. Error: {str(e)}"
        )
