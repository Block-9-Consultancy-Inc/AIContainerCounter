from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel, Field
from prisma.models import ImageTag, ImageWithTag
from prisma.enums import CorrectionType
from server.dependencies import db

router = APIRouter(prefix="/metrics")

class SummaryInput(BaseModel):
    """Represents the summary input in the request body."""
    start_time: datetime = Field(..., description="Start time (utc)")
    end_time: datetime = Field(..., description="End time (utc)")
    user_ids: Optional[List[str]] = Field(..., description="User id filter") 


class UserSummary(BaseModel):
    """Represents the summary details per user."""
    generated_bboxes_reviewed: int = Field(..., description="Number of generated bboxes reviewed")
    user_id: str = Field(..., description="User ID")
    coords_changed: int = Field(..., description="Number of bbox coords changed")
    labels_changed: int = Field(..., description="Number of labels changed")
    bboxes_added: int = Field(..., description="Number of new bboxes added")
    bboxes_removed: int = Field(..., description="Number of bboxes removed")
    num_tasks_complete: int = Field(..., description="Start time (utc)")
    task_ids: List[str] = Field(..., description="Start time (utc)")
    num_images_complete: int = Field(..., description="Start time (utc)")

class OverallSummary(BaseModel):
    """Represents the summary details per user."""
    num_of_images_ready_for_verification: int = Field(..., description="Number of images that are ready for verificaton")
    generated_bboxes_reviewed: int = Field(..., description="Number of generated bboxes reviewed")
    coords_changed: int = Field(..., description="Number of bbox coords changed")
    labels_changed: int = Field(..., description="Number of labels changed")
    bboxes_added: int = Field(..., description="Number of new bboxes added")
    bboxes_removed: int = Field(..., description="Number of bboxes removed")
    num_tasks_complete: int = Field(..., description="Start time (utc)")
    num_images_complete: int = Field(..., description="Start time (utc)")
    num_users: int = Field(..., description="Number of users active in this date range")

class SummaryResponse(BaseModel):
    """Response body model"""
    overall_summary: OverallSummary = Field(..., description="Overall summary for date range given")
    per_user_summary: List[UserSummary] = Field([], description="Summary metrics per user")
    
class NumImagesReadyResponse(BaseModel):
    num_of_images_ready_for_verification: int = Field(..., description="Number of images that are ready for verificaton")


@router.get("/num-images-ready", response_model=NumImagesReadyResponse, tags=["Metrics"])
async def get_num_of_images_ready():
    num_of_images_ready_for_verification: int = (await db.query_first('SELECT COUNT(DISTINCT id) as count FROM "Image" WHERE "imageStatus" = \'ON_QUEUE\';')).get('count', 0)
    return NumImagesReadyResponse(
        num_of_images_ready_for_verification=num_of_images_ready_for_verification
    )

def raw_sql_list(start_index: int, length: int) -> str:
    if length <= 0:
        return '()'
    raw_sql_list = '('
    i = 0
    while i < length - 1:
        raw_sql_list += f'${i + start_index}, '
        i += 1
    raw_sql_list +=f'${start_index + length - 1})'
    return raw_sql_list

@router.post("/summary", response_model=SummaryResponse, tags=["Metrics"])
async def get_summary(
    input: SummaryInput
):  
    num_of_images_ready_for_verification: int = (await db.query_first('SELECT COUNT(DISTINCT id) as count FROM "Image" WHERE "imageStatus" = \'ON_QUEUE\';')).get('count', 0)
    
    overall_summary = OverallSummary(
        num_of_images_ready_for_verification=num_of_images_ready_for_verification,
        generated_bboxes_reviewed=0,
        coords_changed=0,
        labels_changed=0,
        bboxes_added=0,
        bboxes_removed=0,
        num_tasks_complete=0,
        num_images_complete=0,
        num_users=0,
    )

    per_user_summaries: dict[str, UserSummary] = {}
    
    correction_type_per_user_result = await db.query_raw(f'''
        SELECT COUNT(DISTINCT c.id) as "corr_count", c."correctionType", vs."userId"
        FROM "VerificationSession" vs LEFT JOIN "Correction" c ON c."verificationSessionId" = vs.id
        WHERE vs."timeCompleted" IS NOT NULL AND vs."timeAssigned" > $1::timestamp without time zone AND vs."timeAssigned" < $2::timestamp without time zone AND c."correctionType" IS NOT NULL {f'AND vs."userId" IN {raw_sql_list(3, len(input.user_ids))}' if input.user_ids else ''}
        GROUP BY vs."userId", c."correctionType";''', input.start_time, input.end_time, *(input.user_ids if input.user_ids else []))
    
    tasks_per_user_result = await db.query_raw(f'''
        SELECT COUNT(DISTINCT bb.id) as "bbox_count", COUNT(DISTINCT i.id) AS "image_count", COUNT(DISTINCT vs.id) AS "task_count", vs."userId", ARRAY_AGG(DISTINCT vs.id) as "task_ids"
        FROM "Image" i 
                LEFT JOIN "BBox" bb ON bb."imageId" = i.id
                LEFT JOIN "ImageInVerificationSession" ivs ON i.id = ivs."imageId"
                LEFT JOIN "VerificationSession" vs ON vs.id = ivs."verificationSessionId"
        WHERE vs."timeCompleted" IS NOT NULL AND vs."timeAssigned" > $1::timestamp without time zone AND vs."timeAssigned" < $2::timestamp without time zone AND vs."userId" IS NOT NULL {f'AND vs."userId" IN {raw_sql_list(3, len(input.user_ids))}' if input.user_ids else ''}
        GROUP BY vs."userId";''', input.start_time, input.end_time, *(input.user_ids if input.user_ids else []))
    
    overall_summary.num_users = len(tasks_per_user_result)

    for task_per_user in tasks_per_user_result:
        user_id = task_per_user.get('userId')
        task_count = task_per_user.get('task_count')
        image_count = task_per_user.get('image_count')
        task_ids = task_per_user.get('task_ids')
        bbox_count = task_per_user.get('bbox_count')
        per_user_summaries[user_id] = UserSummary(
            user_id=user_id,
            generated_bboxes_reviewed=bbox_count,
            coords_changed=0,
            labels_changed=0,
            bboxes_added=0,
            bboxes_removed=0,
            num_tasks_complete=task_count,
            num_images_complete=image_count,
            task_ids=task_ids
        )
        overall_summary.num_tasks_complete += task_count
        overall_summary.num_images_complete += image_count
        overall_summary.generated_bboxes_reviewed += bbox_count

    for correction_type_per_user in correction_type_per_user_result:
        user_id = correction_type_per_user.get('userId')
        correction_type = correction_type_per_user.get('correctionType')
        correction_type_count = correction_type_per_user.get('corr_count')
        match correction_type:
            case CorrectionType.CHANGED_LABEL:
                per_user_summaries[user_id].labels_changed += correction_type_count
                overall_summary.labels_changed += correction_type_count
            case CorrectionType.CHANGED_COORDS:
                per_user_summaries[user_id].coords_changed += correction_type_count
                overall_summary.coords_changed += correction_type_count
            case CorrectionType.ADDED_MISSING:
                per_user_summaries[user_id].bboxes_added += correction_type_count
                overall_summary.bboxes_added += correction_type_count
            case CorrectionType.REMOVED_EXTRA:
                per_user_summaries[user_id].bboxes_removed += correction_type_count
                overall_summary.bboxes_removed += correction_type_count

    return SummaryResponse(
        overall_summary=overall_summary,
        per_user_summary=list(per_user_summaries.values())
    )