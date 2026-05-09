from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException, status, APIRouter
from pydantic import BaseModel, Field
from prisma.models import Image, DatasetSnapshot
from prisma.enums import DatasetSplit, BBoxType
import random
import traceback
from server.dependencies import db

router = APIRouter(prefix="/datasetsnapshots")

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

# endregion DatasetSnapshot Models



def chunk_id_to_split(chunk_id: str, seed = '42'):
    random.seed(hash((chunk_id, seed)))
    values = [DatasetSplit.TRAIN, DatasetSplit.VALID, DatasetSplit.TEST]

    probabilities = [0.7, 0.2, 0.1]
    return random.choices(values, weights=probabilities, k=1)[0]

def roboflow_image_file_name_to_id(roboflow_image_file_name: str):
    split_index = 0 if roboflow_image_file_name.count('_') == 2 else 1 
    return roboflow_image_file_name.split('_')[split_index]

# --- API Endpoints ---


@router.post(
    "/",
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


@router.get(
    "/{snapshot_id}",
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