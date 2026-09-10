from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlite_db_bare import Batch, MultiContainerImage, BBox, SingleContainerImage, get_all_batches_from_day, get_batch_multi_container_images, get_batch_single_container_images
import requests
import uuid
import sys

chunk_threshold = timedelta(seconds=3) 

# Counting Strategy
DUAL_MODEL_SNAPSHOT: str = 'DUAL_MODEL_SNAPSHOT'
YOLO_CONSENSUS: str = 'YOLO_CONSENSUS'
SIMPLE_COUNT: str = 'SIMPLE_COUNT'

# Model Type
YOLO_CONTAINER = 'YOLO_CONTAINER'
YOLO_CATEGORY = 'YOLO_CATEGORY'
RESNET_CATEGORY = 'RESNET_CATEGORY'

class BaseModelWithSerialization(BaseModel):
    class Config:
        # Ensures datetime is serialized in ISO 8601 format
        json_encoders = {
            datetime: lambda v: v.astimezone(timezone.utc).isoformat()
        }

class RegisterCountiUnitInput(BaseModel):
    id: str = Field(..., description="The id of the new Counti unit (the MAC address of the hardware).")
    location: str = Field(..., description="The location of the unit.")


class RegisterCountiResponse(BaseModel):
    message: Optional[str] = Field(None, description="A message detailing registration status.") 


class BBoxInImageInput(BaseModel):
    id: str
    tracker_id: Optional[int] = None
    x1: int
    y1: int
    x2: int
    y2: int
    label: str

class ImageInBatchInput(BaseModel):
    image_id: str
    file_extension: str
    index: int
    height: int
    width: int
    time_taken: datetime
    chunk_id: str
    bboxes: List[BBoxInImageInput]

    class Config:
        # Ensures datetime is serialized in ISO 8601 format
        json_encoders = {
            datetime: lambda v: v.astimezone(timezone.utc).isoformat()
        }


class VideoInBatchInput(BaseModel):
    file_extension: str
    height: int
    width: int

class BatchInput(BaseModel):
    id: str = Field(...,  description="The UUID of the Batch.")
    count: int
    can_count: int
    plastic_count: int
    gabletop_count: int
    drinkbox_count: int
    pouch_count: int
    time_started: datetime
    time_submitted: datetime
    misc_notes: Optional[str]
    area_collected: Optional[str]
    batch_type: str
    batch_id_by_type: Optional[str]
    container_model_id: Optional[str]
    category_model_id: Optional[str]
    counting_strategy: str
    images: List[ImageInBatchInput]
    tags: Optional[List[str]]
    video: Optional[VideoInBatchInput]

    class Config:
        # Ensures datetime is serialized in ISO 8601 format
        json_encoders = {
            datetime: lambda v: v.astimezone(timezone.utc).isoformat()
        }


class UploadDailyCountiMetadataInput(BaseModel):
    counti_unit_id: str = Field(..., description='The ID of the Counti unit that collected the batches')
    batches: List[BatchInput] = Field(..., description='The list of batches to upload')

class UploadDailyCountiMetadataResponse(BaseModel):
    batches_saved: int = Field(0)
    videos_saved: int = Field(0)
    images_saved: int = Field(0)
    bboxes_saved: int = Field(0)

class TrainedModelCreate(BaseModel):
    id: Optional[str] = Field(..., description="Optional UUID of trained model")
    modelType: str = Field(..., description="Type of the model (e.g., YOLO_CONTAINER).")
    datasetSnapshotId: Optional[str] = Field(None, description="UUID of the DatasetSnapshot used for training.")
    description: Optional[str] = Field(None, description="Optional description for the trained model.")
    checkpointId: Optional[str] = Field(None, description="Optional UUID of the base model checkpoint used for training.")

# Output model for representing a TrainedModel
class TrainedModelResponse(BaseModel):
    id: str = Field(..., description="The UUID of the Trained Model.")
    modelType: str = Field(..., description="Type of the model.")
    description: Optional[str] = Field(None, description="Description of the model.")
    trained: datetime = Field(..., description="Timestamp when the model training finished/metadata was recorded.")
    checkpointId: Optional[str] = Field(None, description="UUID of the base model checkpoint, if any.")
    datasetSnapshotId: Optional[str] = Field(None, description="UUID of the DatasetSnapshot used for training.")

    class Config:
        from_attributes = True

        # Ensures datetime is serialized in ISO 8601 format
        json_encoders = {
            datetime: lambda v: v.astimezone(timezone.utc).isoformat()
        }


def image_to_image_input(image: MultiContainerImage, prev_chunk_id: uuid.UUID, prev_time_taken: datetime, single_container_images: list[SingleContainerImage]) -> ImageInBatchInput:
    chunk_id: uuid.UUID = None
    if prev_chunk_id is not None and prev_time_taken is not None and (image.time_collected - prev_time_taken) < chunk_threshold:
        chunk_id = prev_chunk_id
    else:
        chunk_id = uuid.uuid4()

    # results = model.predict(f'{SRC_DIR}/{image.batch_id}/multi_container_images/{image.id}.{image.index_value}.jpg')[0]
    # detections = Detections.from_ultralytics(results)

    # bboxes: list[BBoxInImageInput] = []

    # for xyxy, class_id in zip(detections.xyxy, detections.class_id):
    #     bboxes.append(
    #         BBoxInImageInput(
    #             id=str(uuid.uuid4()),
    #             x1=int(xyxy[0]),
    #             y1=int(xyxy[1]),
    #             x2=int(xyxy[2]),
    #             y2=int(xyxy[3]),
    #             label=model.names[class_id],
    #         )
    #     )

    bboxes_raw: list[BBox] = list(image.bboxes)

    bboxes: list[BBoxInImageInput] = []

    for bbox_raw in bboxes_raw:
        single_container_image = list(filter(lambda e: e.tracker_id == bbox_raw.tracker_id, single_container_images))
        if len(single_container_image) > 0:
            label = single_container_image[0].predicted_category
        else:
            label = 'container'
        bboxes.append(BBoxInImageInput(
            id=str(bbox_raw.id),
            tracker_id=bbox_raw.tracker_id,
            x1=bbox_raw.x1,
            y1=bbox_raw.y1,
            x2=bbox_raw.x2,
            y2=bbox_raw.y2,
            label=label
        ))

    return ImageInBatchInput(
        image_id=str(image.id),
        file_extension='jpg',
        index=image.index,
        height=image.height,
        width=image.width,
        chunk_id=str(chunk_id),
        time_taken=image.time_collected,
        bboxes=bboxes
    )

model_map = {'batch-32-42-container-model-v3.pt': '58d949dd-ace4-4f34-bf96-fdfde0428a73', 'resnet_v1_18_unscaled.pth': '0f82e57f-7407-47de-9e35-bcbe64c09b27', 'counti-auto-annotator.pt': '839114d0-944f-4515-8680-96001db37dd6', 'mdc-counti-container-2025-03-11.pt': '82675dfb-0401-4a37-a583-34a609c244fe', 'mdc-counti-container-2025-03-14.pt': '5bf4e640-3f05-4043-8f03-df5df62b3d3a', 'mdc-counti-container-2025-03-20.pt': 'ca700b9a-cfab-47cb-ac1a-4583f58b386c', 'mdc-counti-container-2025-03-25.pt': '626e6296-3d18-40ef-ba5d-ace3727718ef', 'mdc-counti-container-2025-04-03.pt': '730a25d8-fa50-4eac-b714-bfe20df9964e', 'mdc-counti-container-2025-04-16.pt': '1f83517c-eb31-4f69-80e5-53164193d28b', 'mdc-counti-container-2025-04-20.pt': 'a947198e-038e-4b11-a2c2-fc314b5e63d5', 'resnet_18_2025-03-11.pth': '37eaeae4-2f20-4103-9b47-d6470d32b54e', 'resnet_18_2025-03-14.pth': 'a48f4f1c-167f-4de7-9d03-5ed4454f7780', 'resnet_18_2025-03-20.pth': '393a658f-a011-4405-ae50-c2f05673fa3b', 'resnet_18_2025-03-25.pth': '7870970e-7597-4883-b2c1-cfc1811b35cc', 'resnet_18_2025-04-03.pth': 'b4b85d30-c74c-4ad8-93ac-510257806d7d', 'resnet_18_2025-04-16.pth': '60adb391-8a5b-4542-9909-ad4cf6a97519', 'resnet_18_2025-04-20.pth': 'e2b8870e-b1a6-4579-9ce2-f706198ccc2f', 'mdc-counti-category-2025-03-20.pt': 'fa2b0479-c7ef-4a25-afce-3d9e9bc86aac', 'mdc-counti-category-2025-03-25.pt': '3f350c52-92e2-4b57-af14-5ccdcf5fa5db', 'mdc-counti-category-2025-04-03.pt': '672feb5a-8ecc-447b-879a-ab32c64ae3bc', 'mdc-counti-category-2025-04-16.pt': '97d8229b-2f1a-4bde-9486-f17741611c9a', 'mdc-counti-category-2025-04-20.pt': '9d04b6b2-5ab7-4dc0-9f9e-3bc853727f67'}


def batch_to_batch_input(batch: Batch) -> BatchInput:
    raw_images: list[MultiContainerImage] = get_batch_multi_container_images(batch.id)
    print(f'images: {len(raw_images)}')
    print(f'time submitted: {batch.time_submitted}')

    single_container_images: list[SingleContainerImage] = get_batch_single_container_images(batch)
    images: list[ImageInBatchInput] = []

    prev_chunk_id: uuid.UUID = None
    prev_time_taken: datetime = None
    for raw_image in raw_images:
        image = image_to_image_input(raw_image, prev_chunk_id, prev_time_taken, single_container_images)
        images.append(image)
        prev_chunk_id = image.chunk_id
        prev_time_taken = image.time_taken

    return BatchInput(
        id=str(batch.id),
        count=batch.count,
        can_count=batch.can_count,
        plastic_count=batch.plastic_count,
        drinkbox_count=batch.drinkbox_count,
        gabletop_count=batch.gabletop_count,
        pouch_count=batch.pouch_count,
        time_started=batch.time_started,
        time_submitted=batch.time_submitted if batch.time_submitted is not None else batch.time_started,
        misc_notes=None,
        area_collected=batch.area_collected,
        # batch_type='EXPRESS' if batch.express_qr_code is not None else 'EAZYPICKUP',
        batch_type='DENSIFIER',
        # batch_id_by_type=batch.express_qr_code if batch.express_qr_code is not None else batch.eazy_pickup_id,
        batch_id_by_type=None,
        category_model_id=model_map.get(batch.category_model),
        container_model_id=model_map.get(batch.yolo_model),
        counting_strategy=DUAL_MODEL_SNAPSHOT,
        images=images,
        tags=None,
        video=None
    )

def upload_daily_counti_metadata_input_for_day(day: datetime) -> UploadDailyCountiMetadataInput:
    print(f'uploading metadata for day: {day}')
    raw_batches = get_all_batches_from_day(day)
    batches = list(filter(lambda e: len(e.images) > 0 and e.batch_id_by_type is not None, map(batch_to_batch_input, raw_batches)))

    if len(batches) == 0:
        print(f'no batches on day: {day}')
        return

    input = UploadDailyCountiMetadataInput(
        counti_unit_id='de:b7:e0:a3:6b:03',
        batches=batches
    )

    response = requests.post(
        "http://192.168.1.204:8000/counti/upload-daily-counti-metadata/",
        data=input.model_dump_json(),
        headers={"api-key": "" },
    )

    response_details = response.content

    print(response_details)


def register_counti_unit():
    input = RegisterCountiUnitInput(
        id='de:b7:e0:a3:6b:03',
        location='Eazy Return Sapperton Return-It Depot'
    )

    response = requests.post('http://label-studio.recyclorobo.ai:8080/register-counti-unit', data=input.model_dump_json())

    response_details = response.content

    print(response_details)


def upload_models():
    inputs = [
        TrainedModelCreate(
            id='58d949dd-ace4-4f34-bf96-fdfde0428a73',
            modelType=YOLO_CONTAINER,
            description="batch-32-42-container-model-v3.pt"
        ),
        TrainedModelCreate(
            id='0f82e57f-7407-47de-9e35-bcbe64c09b27',
            modelType=RESNET_CATEGORY,
            description="resnet_v1_18_unscaled.pth"
        ),
        TrainedModelCreate(
            id='839114d0-944f-4515-8680-96001db37dd6',
            modelType=YOLO_CATEGORY,
            description="counti-auto-annotator.pt"
        ),
        TrainedModelCreate(
            id='82675dfb-0401-4a37-a583-34a609c244fe',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-03-11.pt"
        ),
        TrainedModelCreate(
            id='5bf4e640-3f05-4043-8f03-df5df62b3d3a',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-03-14.pt"
        ),
        TrainedModelCreate(
            id='ca700b9a-cfab-47cb-ac1a-4583f58b386c',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-03-20.pt"
        ),
        TrainedModelCreate(
            id='626e6296-3d18-40ef-ba5d-ace3727718ef',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-03-25.pt"
        ),
        TrainedModelCreate(
            id='730a25d8-fa50-4eac-b714-bfe20df9964e',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-04-03.pt"
        ),
        TrainedModelCreate(
            id='1f83517c-eb31-4f69-80e5-53164193d28b',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-04-16.pt"
        ),
        TrainedModelCreate(
            id='a947198e-038e-4b11-a2c2-fc314b5e63d5',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-04-20.pt"
        ),
        TrainedModelCreate(
            id='37eaeae4-2f20-4103-9b47-d6470d32b54e',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025-03-11.pth"
        ),
        TrainedModelCreate(
            id='a48f4f1c-167f-4de7-9d03-5ed4454f7780',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025-03-14.pth"
        ),
        TrainedModelCreate(
            id='393a658f-a011-4405-ae50-c2f05673fa3b',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025-03-20.pth"
        ),
        TrainedModelCreate(
            id='7870970e-7597-4883-b2c1-cfc1811b35cc',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025-03-25.pth"
        ),
        TrainedModelCreate(
            id='b4b85d30-c74c-4ad8-93ac-510257806d7d',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025-04-03.pth"
        ),
        TrainedModelCreate(
            id='60adb391-8a5b-4542-9909-ad4cf6a97519',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025-04-16.pth"
        ),
        TrainedModelCreate(
            id='e2b8870e-b1a6-4579-9ce2-f706198ccc2f',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025-04-20.pth"
        ),
        TrainedModelCreate(
            id='fa2b0479-c7ef-4a25-afce-3d9e9bc86aac',
            modelType=YOLO_CATEGORY,
            description="mdc-counti-category-2025-03-20.pt"
        ),
        TrainedModelCreate(
            id='3f350c52-92e2-4b57-af14-5ccdcf5fa5db',
            modelType=YOLO_CATEGORY,
            description="mdc-counti-category-2025-03-25.pt"
        ),
        TrainedModelCreate(
            id='672feb5a-8ecc-447b-879a-ab32c64ae3bc',
            modelType=YOLO_CATEGORY,
            description="mdc-counti-category-2025-04-03.pt"
        ),
        TrainedModelCreate(
            id='97d8229b-2f1a-4bde-9486-f17741611c9a',
            modelType=YOLO_CATEGORY,
            description="mdc-counti-category-2025-04-16.pt"
        ),
        TrainedModelCreate(
            id='9d04b6b2-5ab7-4dc0-9f9e-3bc853727f67',
            modelType=YOLO_CATEGORY,
            description="mdc-counti-category-2025-04-20.pt"
        ),
    ]

    model_map = {}

    for input in inputs:
        # response = requests.post('http://label-studio.recyclorobo.ai:8080/trainedmodels', data=input.model_dump_json())

        # print(response.content)
        model_map[input.description] = input.id

    print(model_map)

def get_images_for_day(day: datetime):
    batches = get_all_batches_from_day(day)
    images = []
    for batch in batches:
        batch_images = get_batch_multi_container_images(batch.id)
        print(f'Batch {batch.id}: {len(batch_images)}')
        images.extend(batch_images)
    print(f'{day}: {len(images)}')
    return images

if __name__ == '__main__':
    # procedure = int(sys.argv[1])

    # starting_day = datetime(2025, 8, 7)
    # for i in range(7):
    #     upload_daily_counti_metadata_input_for_day(starting_day + timedelta(days=i))

    now = datetime.now() - timedelta(days=1)
    get_images_for_day(now)

    # if procedure == 1:
    #     register_counti_unit()

    #     upload_models()

    #     day = datetime(2025, 3, 14)

    #     upload_daily_counti_metadata_input_for_day(day)
    # elif procedure == 2:
    #     day = datetime(2025, 3, 15)

    #     upload_daily_counti_metadata_input_for_day(day)
    # elif procedure == 3:
    #     day = datetime(2025, 3, 18)

    #     upload_daily_counti_metadata_input_for_day(day)
    # else:
    #     print(f'no procedures with index {procedure} available')
