import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from prisma import Prisma
from prisma.models import Image, Video, DatasetSnapshot, Batch, BBox
from prisma.enums import DatasetSplit, BBoxType, CountiUnitStatus, CountingStrategy, ModelType # Import the enum from generated types
from prisma.errors import PrismaError, RecordNotFoundError
import random
import uuid
import traceback

# Load environment variables from .env file
load_dotenv()

# Initialize Prisma Client
db = Prisma(auto_register=True)

# --- Pydantic Models for API Input/Output ---

# Represents a bounding box from Roboflow
class BBoxData(BaseModel):
    center_x: float = Field(..., description="The center x coordinate of the bounding box normalized by image width.")
    center_y: float = Field(..., description="The center y coordinate of the bounding box normalized by image height.")
    width: float = Field(..., description="The width of the bounding box normalized by the image width.")
    height: float = Field(..., description="The height of the bounding box normalized by the image height.")
    label: str = Field(..., description="The assigned label of the BBox.")


# Represents an image and its assigned split for creation input
class ImageSplitInput(BaseModel):
    roboflowFileName: str = Field(..., description="The UUID of the Image to include.")
    image_height: int = Field(..., description="The Image height in pixels.")
    image_width: int = Field(..., description="The Image width in pixels.")
    bboxes: List[BBoxData] = Field(..., description="The list of verified bounding boxes on the Image.")

# Input model for creating a new DatasetSnapshot
class DatasetSnapshotCreate(BaseModel):
    description: Optional[str] = Field(None, description="Optional description for the snapshot.")
    images: List[ImageSplitInput] = Field(..., description="List of newly verified roboflow images and their annotations.")
    random_subsample_percentage: Optional[float] = Field(None, description="An optional random subsample percentage to incorporate old data into the newly-created dataset snapshot.")

# Represents an image included in a snapshot for response output
class ImageInSnapshotResponse(BaseModel):
    image_id: str = Field(..., description="The UUID of the included Image.")
    batch_id: str = Field(..., description="The UUID of the batch of the Image.")
    file_extension: str = Field(..., description="The file extension of the included Image.")
    image_height: int = Field(..., description="The Image height in pixels.")
    image_width: int = Field(..., description="The Image width in pixels.")
    bboxes: List[BBoxData] = Field(..., description="The list of verified bounding boxes on the Image.")
    split: DatasetSplit = Field(..., description="The dataset split assigned to this image.")

# Output model for representing a DatasetSnapshot
class DatasetSnapshotResponse(BaseModel):
    id: str = Field(..., description="The UUID of the Dataset Snapshot.")
    description: Optional[str] = Field(None, description="Description of the snapshot.")
    created: datetime = Field(..., description="Timestamp when the snapshot was created.")
    classes: List[str] = Field(..., description="List of classes included in the snapshot.")
    train: List[ImageInSnapshotResponse] = Field(..., description="List of train images included in the snapshot.")
    valid: List[ImageInSnapshotResponse] = Field(..., description="List of valid images included in the snapshot.")
    test: List[ImageInSnapshotResponse] = Field(..., description="List of test images included in the snapshot.")

    # Pydantic configuration for ORM mode (helps map Prisma models) - may not be strictly necessary with manual mapping
    # class Config:
    #     orm_mode = True # or from_attributes = True for Pydantic V2+

    @classmethod
    async def from_dataset_snapshot(cls, snapshot: DatasetSnapshot):
        classes = list(map(lambda e: e.get('label'), await db.query_raw('SELECT DISTINCT b.label FROM "DatasetSnapshot" ds LEFT JOIN "ImageInDatasetSnapshot" ids ON ids."datasetSnapshotId" = ds.id LEFT JOIN "BBox" b on b."imageId" = ids."imageId" WHERE ds.id = ($1)::uuid AND b.label IS NOT NULL', snapshot.id)))
        train = []
        valid = []
        test = []

        for img_in_snap in snapshot.imageInDatasetSnapshot:
            data = ImageInSnapshotResponse(
                image_id=img_in_snap.imageId,
                batch_id=img_in_snap.image.batchId,
                file_extension=img_in_snap.image.fileExtension,
                image_height=img_in_snap.image.height,
                image_width=img_in_snap.image.width,
                bboxes=[BBoxData(
                    center_x=(bbox_in_image_snap.x1 + (bbox_in_image_snap.x2 - bbox_in_image_snap.x1) / 2) / img_in_snap.image.width,
                    center_y=(bbox_in_image_snap.y1 + (bbox_in_image_snap.y2 - bbox_in_image_snap.y1) / 2) / img_in_snap.image.height,
                    width=(bbox_in_image_snap.x2 - bbox_in_image_snap.x1) / img_in_snap.image.width,
                    height=(bbox_in_image_snap.y2 - bbox_in_image_snap.y1) / img_in_snap.image.height,
                    label=bbox_in_image_snap.label,
                ) for bbox_in_image_snap in img_in_snap.image.bboxes],
                split=img_in_snap.split
            )
            if data.split == DatasetSplit.TRAIN:
                train.append(data)
            elif data.split == DatasetSplit.VALID:
                valid.append(data)
            else:
                test.append(data)

        return cls(
            id=snapshot.id,
            description=snapshot.description,
            created=snapshot.created,
            classes=classes,
            train=train,
            valid=valid,
            test=test
        )
    
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
    video: Optional[VideoInBatchInput]

class UploadDailyCountiMetadataInput(BaseModel):
    counti_unit_id: str = Field(..., description='The ID of the Counti unit that collected the batches')
    batches: List[BatchInput] = Field(..., description='The list of batches to upload')

class UploadDailyCountiMetadataResponse(BaseModel):
    batches_saved: int = Field(0)
    videos_saved: int = Field(0)
    images_saved: int = Field(0)
    bboxes_saved: int = Field(0)

# endregion DatasetSnapshot Models

# region TrainedModel Models
# Input model for creating a single TrainedModel metadata entry
class TrainedModelCreate(BaseModel):
    id: Optional[str] = Field(..., description="Optional UUID of trained model")
    modelType: ModelType = Field(..., description="Type of the model (e.g., YOLO_CONTAINER).")
    datasetSnapshotId: Optional[str] = Field(None, description="UUID of the DatasetSnapshot used for training.")
    description: Optional[str] = Field(None, description="Optional description for the trained model.")
    checkpointId: Optional[str] = Field(None, description="Optional UUID of the base model checkpoint used for training.")

# Output model for representing a TrainedModel
class TrainedModelResponse(BaseModel):
    id: str = Field(..., description="The UUID of the Trained Model.")
    modelType: ModelType = Field(..., description="Type of the model.")
    description: Optional[str] = Field(None, description="Description of the model.")
    trained: datetime = Field(..., description="Timestamp when the model training finished/metadata was recorded.")
    checkpointId: Optional[str] = Field(None, description="UUID of the base model checkpoint, if any.")
    datasetSnapshotId: Optional[str] = Field(None, description="UUID of the DatasetSnapshot used for training.")

    class Config:
        from_attributes = True

# endregion TrainedModel Models

class BBoxResponse(BaseModel):
    """Pydantic model for representing a BBox in the response."""
    id: str
    label: str
    bboxType: str # Prisma enum maps to string
    x1: int
    y1: int
    x2: int
    y2: int

    class Config:
        from_attributes = True # Enable ORM mode for easy Prisma model conversion

class ImageWithBBoxesResponse(BaseModel):
    """Pydantic model for representing an Image with its BBoxes."""
    id: str
    fileExtension: str
    height: int
    width: int
    timeTaken: datetime
    batchId: str
    chunkId: str
    bboxes: List[BBoxResponse] = [] # Include list of BBoxes

    class Config:
        from_attributes = True

# Define the structure for the cursor.
# We use a tuple: (timeTaken_timestamp, image_id)
# Pydantic doesn't directly support tuples in request bodies easily without custom parsing,
# so we'll accept a dictionary and convert it.
class CursorInput(BaseModel):
    """Represents the cursor input in the request body."""
    time_taken: datetime
    image_id: str

class PaginationRequest(BaseModel):
    """Request body model for pagination parameters."""
    limit: int = Field(10, gt=0, le=5000, description="Number of items per page (max 100)")
    contains_verified_bboxes: bool
    # Use the CursorInput model for the cursor field
    cursor: Optional[CursorInput] = Field(None, description="Cursor for pagination (time_taken and image_id of the last item from the previous page)")
    sort_order: str = Field("asc", pattern="^(asc|desc)$", description="Sort order for 'timeTaken' ('asc' or 'desc')")

class PaginatedImageResponse(BaseModel):
    """Response model containing the list of images and the next cursor."""
    images: List[ImageWithBBoxesResponse]
    # The next cursor will also be represented as a dictionary for consistency
    next_cursor: Optional[Dict[str, Any]] = Field(None, description="Cursor for fetching the next page {time_taken: ..., image_id: ...}")


# --- FastAPI Application Setup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect the Prisma client on application startup
    print("Connecting to database...")
    await db.connect()
    yield
    # Disconnect the Prisma client on application shutdown
    print("Disconnecting from database...")
    if db.is_connected():
        await db.disconnect()

# Create FastAPI app instance with lifespan management
app = FastAPI(
    title="Counti API",
    description="API for managing Counti datasets and models.",
    version="1.0.0",
    lifespan=lifespan
)

def chunk_id_to_split(chunk_id: str, seed = '42'):
    random.seed(hash((chunk_id, seed)))
    values = [DatasetSplit.TRAIN, DatasetSplit.VALID, DatasetSplit.TEST]

    probabilities = [0.7, 0.2, 0.1]
    return random.choices(values, weights=probabilities, k=1)[0]

def roboflow_image_file_name_to_id(roboflow_image_file_name: str):
    split_index = 0 if roboflow_image_file_name.count('_') == 2 else 1 
    return roboflow_image_file_name.split('_')[split_index]

# --- API Endpoints ---

@app.post(
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

@app.post(
    "/upload-daily-counti-metadata/",
    response_model=UploadDailyCountiMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Uploads daily Counti metadata (all images and annotations at end of day)",
    tags=["Counti Metadata"]
)
async def upload_daily_counti_metadata(input: UploadDailyCountiMetadataInput):
    try:
        batches = []
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
                    chunkId=image.chunk_id
                ).model_dump(exclude_none=True))

                for bbox in image.bboxes:
                    id = str(uuid.uuid4())
                    bboxes.append(BBox(
                        id=id,
                        imageId=image.image_id,
                        label=bbox.label,
                        bboxType=BBoxType.DETECTION,
                        x1=bbox.x1,
                        y1=bbox.y1,
                        x2=bbox.x2,
                        y2=bbox.y2
                    ).model_dump(exclude_none=True))

        batches_saved = await db.batch.create_many(data=batches)
        videos_saved = await db.video.create_many(data=videos)
        images_saved = await db.image.create_many(data=images)
        bboxes_saved = await db.bbox.create_many(data=bboxes)
        response = UploadDailyCountiMetadataResponse(
            batches_saved=batches_saved,
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

@app.post(
    "/datasetsnapshots/",
    response_model=DatasetSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Dataset Snapshot",
    tags=["Dataset Snapshots"]
)
async def create_dataset_snapshot(snapshot_data: DatasetSnapshotCreate):
    """
    Creates a new Dataset Snapshot record, linking specified images
    with their designated splits (TRAIN, VALID, TEST).

    - **description**: An optional text description for the snapshot.
    - **images**: A mandatory list where each item specifies an `imageId` (UUID string)
      and its `split` (enum: TRAIN, VALID, or TEST).

    Returns the newly created Dataset Snapshot details including its ID,
    description, creation timestamp, and the list of included images with their splits.

    Raises `HTTPException` (400 Bad Request) if image IDs specified
    in the request do not exist (this check is implicitly handled by Prisma's
    relation constraints if the foreign key exists, but explicit checks could be added).
    """
    try:
        # Prepare the data structure for creating related ImageInDatasetSnapshot records
        image_ids = [
            roboflow_image_file_name_to_id(img.roboflowFileName)
            for img in snapshot_data.images
        ]

        existing_images = {image.id: {'existing': image} for image in (await db.image.find_many(where={ 'id': { 'in': image_ids }}))}
        for roboflow_image in snapshot_data.images:
            existing_image = existing_images.get(roboflow_image_file_name_to_id(roboflow_image.roboflowFileName))
            if existing_image is None:
                continue
            existing_image['roboflow'] = roboflow_image

        image_links_to_create = [
            {'imageId': image_id, 'split': chunk_id_to_split(old_and_new.get('existing').chunkId) }
            for image_id, old_and_new in existing_images.items()
        ]

        bboxes_to_create = []

        for image_id, old_and_new in existing_images.items():
            roboflow_image: ImageSplitInput = old_and_new.get('roboflow')
            existing_image: Image = old_and_new.get('existing')
            bboxes_to_create.extend(list(map(lambda e: {
                'bboxType': BBoxType.ANNOTATION,
                'label': e.label,
                'imageId': existing_image.id,
                'x1': max(0, round((e.center_x - e.width / 2) * roboflow_image.image_width)),
                'y1': max(0, round((e.center_y - e.height / 2) * roboflow_image.image_height)),
                'x2': min(roboflow_image.image_width, round((e.center_x + e.width / 2) * roboflow_image.image_width)),
                'y2': min(roboflow_image.image_height, round((e.center_y + e.height / 2) * roboflow_image.image_height)),
            }, roboflow_image.bboxes)))

        await db.bbox.create_many(data=bboxes_to_create)

        # Create the DatasetSnapshot and its related ImageInDatasetSnapshot entries in one transaction
        new_snapshot = await db.datasetsnapshot.create(
            data={
                'description': snapshot_data.description,
                # Use the 'create' nested write operation for the relation
                'imageInDatasetSnapshot': {
                    'create': image_links_to_create
                }
            },
            # Include the related data in the response from Prisma
            include={'imageInDatasetSnapshot':  { 'include': { 'image': { 'include': { 'bboxes': { 'where': { 'bboxType': BBoxType.ANNOTATION }}}}}}}
        )

        return await DatasetSnapshotResponse.from_dataset_snapshot(new_snapshot)
    
    except Exception as e:
        # Catch potential errors during database operation (e.g., foreign key constraint if imageId doesn't exist)
        # In a production scenario, log the error 'e' and potentially check for specific Prisma/DB errors
        print(f"Error creating dataset snapshot: {e}") # Basic logging
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not create dataset snapshot. Ensure all image IDs exist and data is valid. Error: {str(e)}"
        )


@app.get(
    "/datasetsnapshots/{snapshot_id}",
    response_model=DatasetSnapshotResponse,
    summary="Get a specific Dataset Snapshot by ID",
    tags=["Dataset Snapshots"]
)
async def get_dataset_snapshot(snapshot_id: str):
    """
    Retrieves the details of a specific Dataset Snapshot identified by its UUID.

    - **snapshot_id**: The UUID of the Dataset Snapshot to fetch.

    Returns the Dataset Snapshot details including its ID, description,
    creation timestamp, and the list of included images with their splits.

    Raises `HTTPException` (404 Not Found) if no snapshot exists with the given ID.
    """
    snapshot = await db.datasetsnapshot.find_unique(
        where={'id': snapshot_id},
        include={'imageInDatasetSnapshot': { 'include': { 'image': { 'include': { 'bboxes': { 'where': { 'bboxType': BBoxType.ANNOTATION }} }} }}}  # Ensure related images are fetched
    )

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset Snapshot with ID '{snapshot_id}' not found."
        )
    
    return await DatasetSnapshotResponse.from_dataset_snapshot(snapshot)

def cond_dict(
        cond: bool, cond_dict: dict,
) -> dict:
    return cond_dict if cond else {}

# region Trained Model Endpoints
@app.post(
    "/trainedmodels/",
    response_model=TrainedModelResponse, # Returns a list
    status_code=status.HTTP_201_CREATED,
    summary="Upload metadata for one or more newly trained models",
    tags=["Trained Models"]
)
async def create_trained_model(model_data: TrainedModelCreate):
    """
    Uploads metadata for one or more newly trained models.
    Each item in the list should contain:
    - **modelType**: The type of the model (enum).
    - **datasetSnapshotId**: The UUID of the dataset snapshot used for training.
    - **description**: Optional description.
    - **checkpointId**: Optional UUID of the base model checkpoint.

    Returns a list of the created trained model metadata records.
    Performs creations within a database transaction for atomicity.
    """
    try:
         # Prepare data, handling optional fields explicitly
        create_data = {
            **cond_dict(model_data.id is not None, { 'id': model_data.id }),
            'modelType': model_data.modelType,
            'datasetSnapshotId': model_data.datasetSnapshotId,
            'description': model_data.description,
            # Only include checkpointId if it's provided
            'checkpointId': model_data.checkpointId if model_data.checkpointId else None
        }
        # Remove None values if Prisma client expects only provided fields
        # create_data = {k: v for k, v in create_data.items() if v is not None} # Optional refinement

        new_model = await db.trainedmodel.create(data=create_data)
        return TrainedModelResponse.model_validate(new_model, from_attributes=True)

    except PrismaError as e:
        # Catch specific Prisma/DB errors like foreign key violations
        print(f"Error creating trained model: {e}")
        error_detail = "Could not create trained model. Ensure related DatasetSnapshot and Checkpoint ID exist and data is valid."
        # Example: Check for foreign key violation specifically
        # if e.code == 'P2003': # Prisma error code for foreign key constraint failed
        #    error_detail = f"Could not create models: Invalid datasetSnapshotId or checkpointId provided."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail
        )
    except Exception as e:
        print(f"Unexpected error creating trained models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating trained models."
        )

@app.get(
    "/trainedmodels/latest/",
    response_model=TrainedModelResponse,
    summary="Get the latest trained model, optionally filtered by type",
    tags=["Trained Models"]
)
async def get_latest_trained_model(
    model_type: Optional[ModelType] = Query(None, description="Filter by a specific model type.") # Use Query for better docs/validation
):
    """
    Retrieves the metadata of the most recently trained model based on the 'trained' timestamp.
    Optionally filters by `model_type`.

    - **model_type** (query parameter): If provided, filters for the latest model of this specific type.

    Returns the latest matching trained model's metadata.
    Raises `HTTPException` (404 Not Found) if no models exist or none match the filter.
    """
    where_clause = {}
    if model_type:
        where_clause['modelType'] = model_type

    latest_model = await db.trainedmodel.find_first(
        where=where_clause,
        order_by={'trained': 'desc'} # Order by training timestamp descending
    )

    if not latest_model:
        error_detail = "No trained models found."
        if model_type:
            error_detail = f"No trained models found matching type '{model_type.value}'."
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail
        )

    # Map Prisma model to Pydantic response model
    return TrainedModelResponse.from_orm(latest_model)


@app.get(
    "/trainedmodels/{model_id}",
    response_model=TrainedModelResponse,
    summary="Get a specific trained model by ID",
    tags=["Trained Models"]
)
async def get_trained_model(model_id: str):
    """
    Retrieves the metadata of a specific Trained Model identified by its UUID.

    - **model_id**: The UUID of the Trained Model to fetch.

    Returns the trained model's metadata.
    Raises `HTTPException` (404 Not Found) if no model exists with the given ID.
    """
    try:
        model = await db.trainedmodel.find_unique_or_raise(
             where={'id': model_id}
        )
        # Map Prisma model to Pydantic response model
        return TrainedModelResponse.model_validate(model)
    except RecordNotFoundError:
         raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trained Model with ID '{model_id}' not found."
        )
    except Exception as e:
        print(f"Unexpected error fetching trained model {model_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching the trained model."
        )

# endregion Trained Model Endpoints

@app.post("/images", response_model=PaginatedImageResponse, tags=["Images"])
async def get_paginated_images(
    pagination: PaginationRequest
):
    """
    Retrieves a paginated list of images, including their bounding boxes.

    Supports cursor-based pagination and sorting by 'timeTaken'.

    - **limit**: Max number of images per page.
    - **cursor**: Dictionary containing `time_taken` (ISO 8601 format) and `image_id`
                  from the last item of the previous page to fetch the next page.
                  Send `null` or omit for the first page.
    - **sort_order**: 'asc' (default) or 'desc' for sorting by `timeTaken`.
    """
    try:
        # --- Execute Query ---
        images = await db.image.find_many(
            take=pagination.limit + 1,
            order=[{
                'timeTaken': pagination.sort_order,
            },
            {
                'id': pagination.sort_order
            }
            ],
            where={ 'bboxes': { 'some': { 'bboxType': BBoxType.ANNOTATION }}} if pagination.contains_verified_bboxes else None,
            include={ 'bboxes': True },
            skip=1 if pagination.cursor is not None else 0
        )

        # --- Determine Next Cursor ---
        next_cursor_data = None
        if len(images) > pagination.limit:
            # Remove the extra item used for determining the next cursor
            last_image = images.pop(pagination.limit)
            # Format the next cursor as a dictionary for the response
            next_cursor_data = {
                "time_taken": last_image.timeTaken,
                "image_id": last_image.id
            }

        # --- Format Response ---
        # Convert Prisma models to Pydantic models (including nested BBoxes)
        # This happens automatically if orm_mode=True and models match,
        # but explicit conversion can be clearer if needed.
        response_images = [ImageWithBBoxesResponse.model_validate(img) for img in images]

        return PaginatedImageResponse(
            images=response_images,
            next_cursor=next_cursor_data
        )

    except Exception as e:
        print(f"Error fetching images: {e}")
        # Consider more specific error handling based on potential Prisma errors
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

# --- Root Endpoint for Health Check/Welcome ---
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the Counti API"}

# --- Running the App (for development) ---
# You would typically run this using Uvicorn:
# uvicorn main:app --reload