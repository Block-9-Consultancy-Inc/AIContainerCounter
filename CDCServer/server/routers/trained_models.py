from datetime import datetime
from typing import Optional
from fastapi import HTTPException, Query, status, APIRouter
from pydantic import BaseModel, Field
from prisma.enums import ModelType # Import the enum from generated types
from prisma.errors import PrismaError, RecordNotFoundError
from server.dependencies import db

router = APIRouter(prefix="/trainedmodels")

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



def cond_dict(cond: bool, dict: dict):
    return dict if cond else {}

# region Trained Model Endpoints

@router.post(
    "/",
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

@router.get(
    "/latest/",
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


@router.get(
    "/{model_id}",
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