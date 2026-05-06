from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlite_db_bare import Batch, MultiContainerImage, BBox, SingleContainerImage
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
    container_model_id: Optional[str]
    category_model_id: Optional[str]
    counting_strategy: str
    images: List[ImageInBatchInput]
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



def get_all_batches_from_day(day: datetime):

    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)

    batches = Batch.select().where((Batch.time_started > start) & (Batch.time_started < end))
    
    return list(batches)

def image_to_image_input(image: MultiContainerImage, prev_chunk_id: uuid.UUID, prev_time_taken: datetime, single_container_images: list[SingleContainerImage]) -> ImageInBatchInput:
    chunk_id: uuid.UUID = None
    if prev_chunk_id is not None and prev_time_taken is not None and (image.time_collected - prev_time_taken) < chunk_threshold:
        chunk_id = prev_chunk_id
    else:
        chunk_id = uuid.uuid4()

    bboxes_raw: list[BBox] = list(image.bboxes)

    bboxes: list[BBoxInImageInput] = []

    for bbox_raw in bboxes_raw:
        single_container_image = list(filter(lambda e: e.tracker_id == bbox_raw.tracker_id, single_container_images))
        if len(single_container_image) > 0:
            label = single_container_image[0].predicted_category
        else:
            label = 'container'
        bboxes.append(BBoxInImageInput(
            x1=bbox_raw.x1,
            y1=bbox_raw.y1,
            x2=bbox_raw.x2,
            y2=bbox_raw.y2,
            label=label
        ))

    return ImageInBatchInput(
        image_id=str(image.id),
        file_extension='jpg',
        index=image.index_value,
        height=image.height,
        width=image.width,
        chunk_id=str(chunk_id),
        time_taken=image.time_collected,
        bboxes=bboxes
    )

model_map = {
    "mdc-counti-container-2025-03-11.pt": '82675dfb-0401-4a37-a583-34a609c244fe',
    "mdc-counti-container-2025-03-14.pt": '5bf4e640-3f05-4043-8f03-df5df62b3d3a',
    "mdc-counti-container-2025-03-20.pt": 'ca700b9a-cfab-47cb-ac1a-4583f58b386c',
    "resnet_18_2025_03_11.pth": '37eaeae4-2f20-4103-9b47-d6470d32b54e',
    "resnet_18_2025_03_14.pth": 'a48f4f1c-167f-4de7-9d03-5ed4454f7780',
    "resnet_18_2025-03-20.pth": '393a658f-a011-4405-ae50-c2f05673fa3b'
}


def batch_to_batch_input(batch: Batch) -> BatchInput:
    raw_images: list[MultiContainerImage] = list(batch.multiContainerImages.order_by(MultiContainerImage.time_collected.asc()))

    single_container_images: list[SingleContainerImage] = list(batch.singleContainerImages)
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
        time_submitted=batch.time_submitted,
        misc_notes=None,
        area_collected=batch.area_collected,
        category_model_id=model_map.get(batch.category_model),
        container_model_id=model_map.get(batch.yolo_model),
        counting_strategy=DUAL_MODEL_SNAPSHOT,
        images=images,
        video=VideoInBatchInput(
            height=1080,
            width=1920,
            file_extension='avi'
        )
    )

def upload_daily_counti_metadata_input_for_day(day: datetime) -> UploadDailyCountiMetadataInput:
    raw_batches = get_all_batches_from_day(day)
    batches = list(map(batch_to_batch_input, raw_batches))

    input = UploadDailyCountiMetadataInput(
        counti_unit_id='test',
        batches=batches
    )

    response = requests.post('http://localhost:8000/upload-daily-counti-metadata', data=input.model_dump_json())

    response_details = response.content

    print(response_details)


def register_counti_unit():
    input = RegisterCountiUnitInput(
        id='test',
        location='vancouver'
    )

    response = requests.post('http://localhost:8000/register-counti-unit', data=input.model_dump_json())

    response_details = response.content

    print(response_details)


def upload_models():
    inputs = [
        TrainedModelCreate(
            id='82675dfb-0401-4a37-a583-34a609c244fe',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-03-11.pt"
        ),
        TrainedModelCreate(
            id='5bf4e640-3f05-4043-8f03-df5df62b3d3a',
            checkpointId='82675dfb-0401-4a37-a583-34a609c244fe',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-03-14.pt"
        ),
        TrainedModelCreate(
            id='ca700b9a-cfab-47cb-ac1a-4583f58b386c',
            checkpointId='5bf4e640-3f05-4043-8f03-df5df62b3d3a',
            modelType=YOLO_CONTAINER,
            description="mdc-counti-container-2025-03-20.pt"
        ),
        TrainedModelCreate(
            id='37eaeae4-2f20-4103-9b47-d6470d32b54e',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025_03_11.pth"
        ),
        TrainedModelCreate(
            id='a48f4f1c-167f-4de7-9d03-5ed4454f7780',
            checkpointId='37eaeae4-2f20-4103-9b47-d6470d32b54e',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025_03_14.pth"
        ),
        TrainedModelCreate(
            id='393a658f-a011-4405-ae50-c2f05673fa3b',
            checkpointId='a48f4f1c-167f-4de7-9d03-5ed4454f7780',
            modelType=RESNET_CATEGORY,
            description="resnet_18_2025-03-20.pth"
        ),
    ]

    for input in inputs:
        response = requests.post('http://localhost:8000/trainedmodels', data=input.model_dump_json())

        print(response.content)

if __name__ == '__main__':
    procedure = int(sys.argv[2])

    if procedure == 0:
        register_counti_unit()

        upload_models()

        day = datetime(2025, 3, 14)

        upload_daily_counti_metadata_input_for_day(day)
    elif procedure == 1:
        day = datetime(2025, 3, 15)

        upload_daily_counti_metadata_input_for_day(day)
    elif procedure == 2:
        day = datetime(2025, 3, 18)

        upload_daily_counti_metadata_input_for_day(day)
    else:
        print(f'no procedures with index {procedure} available')
