from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException, status, APIRouter
from pydantic import BaseModel, Field
from prisma.models import Image, Video, Batch, BBox, BatchWithTag, BatchTag
from prisma.enums import BBoxType, CountiUnitStatus, CountingStrategy, ImageStatus
import traceback
from server.dependencies import db


router = APIRouter(prefix="/counti")

class RegisterCountiUnitInput(BaseModel):
    id: str = Field(..., description="The id of the new Counti unit (the MAC address of the hardware).")
    location: str = Field(..., description="The location of the unit.")


class RegisterCountiResponse(BaseModel):
    message: Optional[str] = Field(None, description="A message detailing registration status.") 


class BBoxInImageInput(BaseModel):
    id: str
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
    counting_strategy: CountingStrategy
    images: List[ImageInBatchInput]
    tags:   Optional[List[str]]
    video: Optional[VideoInBatchInput]

class UploadDailyCountiMetadataInput(BaseModel):
    counti_unit_id: str = Field(..., description='The ID of the Counti unit that collected the batches')
    batches: List[BatchInput] = Field(..., description='The list of batches to upload')

class UploadDailyCountiMetadataResponse(BaseModel):
    batches_saved: int = Field(0)
    tags_created: int = Field(0)
    batch_with_tags_saved: int = Field(0)
    videos_saved: int = Field(0)
    images_saved: int = Field(0)
    bboxes_saved: int = Field(0)



@router.post(
    "/register-counti-unit/",
    response_model=RegisterCountiResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registers a new Counti unit as long as the ID is unique.",
    tags=["Counti Unit"]
)
async def register_new_counti_unit(input: RegisterCountiUnitInput):

    try:
        existing_unit = await db.countiunit.find_unique(where={ 'id': input.id })

        if existing_unit is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Counti unit with this id is already registered."
            )
        
        await db.countiunit.create(data={
            'id': input.id,
            'location': input.location,
            'status': CountiUnitStatus.INITIALIZING,
        })

        return RegisterCountiResponse(
                message=f"Successfully registered new counti unit with id: {input.id}",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to register new counti unit due to error: {e}"
        )

@router.post(
    "/upload-daily-counti-metadata/",
    response_model=UploadDailyCountiMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Uploads daily Counti metadata (all images and annotations at end of day)",
    tags=["Counti Metadata"]
)
async def upload_daily_counti_metadata(input: UploadDailyCountiMetadataInput):
    try:
        tags = set()
        batches = []
        batches_with_tags = []
        videos = []
        images = []
        bboxes = []
        for batch in input.batches:
            batches.append(Batch(
                id=batch.id,
                count=batch.count,
                canCount=batch.can_count,
                plasticCount=batch.plastic_count,
                gabletopCount=batch.gabletop_count,
                drinkboxCount=batch.drinkbox_count,
                pouchCount=batch.pouch_count,
                timeStarted=batch.time_started,
                timeSubmitted=batch.time_submitted,
                miscellaneousNotes=batch.misc_notes,
                areaCollected=batch.area_collected,
                countiUnitId=input.counti_unit_id,
                countingStrategy=batch.counting_strategy,
                containerModelId=batch.container_model_id,
                categoryModelId=batch.category_model_id
            ).model_dump(exclude_none=True))

            if batch.tags is not None and len(batch.tags) > 0:
                tags.update(batch.tags)
                batches_with_tags.extend(list(map(lambda e: BatchWithTag(batchId=batch.id,tagName=e).model_dump(exclude_none=True), batch.tags)))
            
            if batch.video is not None:
                videos.append(Video(
                    batchId=batch.id,
                    fileExtension=batch.video.file_extension,
                    height=batch.video.height,
                    width=batch.video.width
                ).model_dump(exclude_none=True))

            for image in batch.images:
                images.append(Image(
                    id=image.image_id,
                    fileExtension=image.file_extension,
                    index=image.index,
                    height=image.height,
                    width=image.width,
                    timeTaken=image.time_taken,
                    batchId=batch.id,
                    imageStatus=ImageStatus.ON_QUEUE,
                    chunkId=image.chunk_id
                ).model_dump(exclude_none=True))

                for bbox in image.bboxes:
                    bboxes.append(BBox(
                        id=bbox.id,
                        imageId=image.image_id,
                        label=bbox.label,
                        bboxType=BBoxType.DETECTION,
                        x1=bbox.x1,
                        y1=bbox.y1,
                        x2=bbox.x2,
                        y2=bbox.y2
                    ).model_dump(exclude_none=True))

        batches_saved = await db.batch.create_many(data=batches, skip_duplicates=True)
        tags_created = 0
        existing_tags = set(map(lambda e: e.name, await db.batchtag.find_many(where={ 'name' : { 'in': list(tags) }})))
        non_existing_tags = list(tags.difference(existing_tags))
        if len(non_existing_tags) > 0:
            tags_created = await db.batchtag.create_many(list(map(lambda e: BatchTag(name=e).model_dump(exclude_none=True), non_existing_tags)), skip_duplicates=True)
        batches_with_tags_saved = await db.batchwithtag.create_many(batches_with_tags)
        videos_saved = await db.video.create_many(data=videos, skip_duplicates=True)
        images_saved = await db.image.create_many(data=images, skip_duplicates=True)
        bboxes_saved = await db.bbox.create_many(data=bboxes, skip_duplicates=True)
        response = UploadDailyCountiMetadataResponse(
            batches_saved=batches_saved,
            tags_created=tags_created,
            batch_with_tags_saved=batches_with_tags_saved,
            videos_saved=videos_saved,
            images_saved=images_saved,
            bboxes_saved=bboxes_saved
        )
        print(response)
        return response
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to save daily counti metadata due to error: {e}"
        )