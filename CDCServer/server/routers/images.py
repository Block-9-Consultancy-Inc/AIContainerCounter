from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel, Field
from prisma.enums import BBoxType
from server.dependencies import db

router = APIRouter(prefix="/images")

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




@router.post("/", response_model=PaginatedImageResponse, tags=["Images"])
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
