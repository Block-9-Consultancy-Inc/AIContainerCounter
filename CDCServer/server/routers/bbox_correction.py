from datetime import datetime
from prisma.models import Image, DatasetSnapshot, Correction, BBox, ImageInVerificationSession, VerificationSession
from prisma.enums import DatasetSplit, ImageStatus, DatasetSnapshotType, CorrectionType
import copy
import uuid
from PIL import ImageDraw, ImageFont
import PIL
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Configuration ---
IOU_THRESHOLD = 0.9
# Epsilon for floating point comparisons, e.g., to check if IoU is effectively 1.0
FLOAT_COMPARISON_EPSILON = 1e-7

class BBoxData(BaseModel):
    center_x: float = Field(
        ..., description="The center x coordinate of the bounding box normalized by image width.")
    center_y: float = Field(
        ..., description="The center y coordinate of the bounding box normalized by image height.")
    width: float = Field(
        ..., description="The width of the bounding box normalized by the image width.")
    height: float = Field(
        ..., description="The height of the bounding box normalized by the image height.")
    label: str = Field(..., description="The assigned label of the BBox.")


# Represents an image and its assigned split for creation input
class ImageSplitInput(BaseModel):
    roboflowFileName: str = Field(...,
                                  description="The UUID of the Image to include.")
    image_height: int = Field(..., description="The Image height in pixels.")
    image_width: int = Field(..., description="The Image width in pixels.")
    bboxes: List[BBoxData] = Field(
        ..., description="The list of verified bounding boxes on the Image.")

def correction_to_model(image_id: str, correction: dict, verification_session_id: str = None) -> dict:
    if correction.get('type') == 'REMOVED_EXTRA':
        return {
            'imageId': image_id,
            'verificationSessionId': verification_session_id,
            'correctionType': CorrectionType.REMOVED_EXTRA,
            'originalCorrectionId': correction.get('original_correction_id'),
            'originalBBoxId': correction.get("original_bbox_uuid"),
        }
    elif correction.get('type') == 'CHANGED_LABEL':
        return {
            'imageId': image_id,
            'verificationSessionId': verification_session_id,
            'correctionType': CorrectionType.CHANGED_LABEL,
            'newLabel': correction.get('new_label'),
            'originalBBoxId': correction.get("original_bbox_uuid"),
            'originalCorrectionId': correction.get('original_correction_id')
        }
    elif correction.get('type') == 'CHANGED_COORDS':
        return {
            'imageId': image_id,
            'verificationSessionId': verification_session_id,
            'correctionType': CorrectionType.CHANGED_COORDS,
            'originalBBoxId': correction.get("original_bbox_uuid"),
            'originalCorrectionId': correction.get('original_correction_id'),
            'x1': correction.get('new_coords').get('x'),
            'y1': correction.get('new_coords').get('y'),
            'x2': correction.get('new_coords').get('x') + correction.get('new_coords').get('w'),
            'y2': correction.get('new_coords').get('y') + correction.get('new_coords').get('h'),
        }
    elif correction.get('type') == 'ADDED_MISSING':
        return {
            'imageId': image_id,
            'verificationSessionId': verification_session_id,
            'correctionType': CorrectionType.ADDED_MISSING,
            'newLabel': correction.get('added_bbox_data').get('label'),
            'originalCorrectionId': correction.get('original_correction_id'),
            'x1': correction.get('added_bbox_data').get('coords').get('x'),
            'y1': correction.get('added_bbox_data').get('coords').get('y'),
            'x2': correction.get('added_bbox_data').get('coords').get('x') + correction.get('added_bbox_data').get('coords').get('w'),
            'y2': correction.get('added_bbox_data').get('coords').get('y') + correction.get('added_bbox_data').get('coords').get('h'),
        }
    
def model_to_correction(correction: Correction) -> dict:
    match correction.correctionType:
        case CorrectionType.CHANGED_LABEL:
            return {
                "id": correction.id,
                "type": "CHANGED_LABEL",
                "original_correction_id": correction.originalCorrectionId,
                "original_bbox_id": correction.originalBBoxId,
                "new_label": correction.newLabel,
                "final_bbox_data": { 
                    "label": correction.newLabel
                }
            }
        case CorrectionType.CHANGED_COORDS:
            return {
                "id": correction.id,
                "type": "CHANGED_COORDS",
                "original_correction_id": correction.originalCorrectionId,
                "original_bbox_id": correction.originalBBoxId,
                "new_coords": {
                    'x': correction.x1,
                    'y': correction.y1,
                    'w': correction.x2 - correction.x1,
                    'h': correction.y2 - correction.y1
                },
                "final_bbox_data": {
                    "coords": {
                        'x': correction.x1,
                        'y': correction.y1,
                        'w': correction.x2 - correction.x1,
                        'h': correction.y2 - correction.y1
                    },
                },
                "iou_with_original": None
            }
        case CorrectionType.REMOVED_EXTRA:
            return {
                "id": correction.id,
                "type": "REMOVED_EXTRA",
                "original_correction_id": correction.originalCorrectionId,
                "original_bbox_id": correction.originalBBoxId,
                "removed_bbox_details": {
                    "uuid": correction.originalBBoxId, # UUID of the removed box
                }
            }
        case CorrectionType.ADDED_MISSING:
            return {
                "id": correction.id,
                "type": "ADDED_MISSING",
                "original_bbox_id": correction.id,
                "original_correction_id": correction.originalCorrectionId,
                "added_bbox_data": { # No original UUID for the added box itself
                    "coords": {
                        'x': correction.x1,
                        'y': correction.y1,
                        'w': correction.x2 - correction.x1,
                        'h': correction.y2 - correction.y1
                    },
                    "label": correction.newLabel
                }
            }

class BoundingBox:
    """
    Represents a bounding box with its properties.
    'uuid' can be an original UUID (for 'before' boxes) or a temporary one (for 'after' boxes).
    """
    def __init__(self, x, y, w, h, label, id_val=None, original_correction_id=None): # id_val is the UUID or temporary ID
        self.uuid = str(id_val) if id_val is not None else None # Store ID as string
        self.original_correction_id = original_correction_id
        try:
            self.x1 = int(x)
            self.y1 = int(y)
            self.w = int(w)
            self.h = int(h)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Coordinates (x,y,w,h) must be numeric. Error for ID '{self.uuid}': {e}"
            )

        if self.w < 0 or self.h < 0:
            raise ValueError(
                f"Width and height must be non-negative. Got w={self.w}, h={self.h} for ID '{self.uuid}'"
            )
        
        self.x2 = self.x1 + self.w
        self.y2 = self.y1 + self.h
        self.label = str(label)
        self.area = self.w * self.h

    @property
    def coords_xywh(self):
        """Returns coordinates in {x, y, w, h} format."""
        return {'x': self.x1, 'y': self.y1, 'w': self.w, 'h': self.h}

    def __repr__(self):
        id_str = f"uuid={self.uuid}" if self.uuid else "no_id"
        return (f"BBox({id_str}, label='{self.label}', "
                f"x={self.x1}, y={self.y1}, w={self.w}, h={self.h})")

def calculate_iou(box1: BoundingBox, box2: BoundingBox) -> float:
    """
    Calculates the Intersection over Union (IoU) between two bounding boxes.
    """
    xi1 = max(box1.x1, box2.x1)
    yi1 = max(box1.y1, box2.y1)
    xi2 = min(box1.x2, box2.x2)
    yi2 = min(box1.y2, box2.y2)

    inter_width = max(0, xi2 - xi1)
    inter_height = max(0, yi2 - yi1)
    inter_area = inter_width * inter_height

    box1_area = box1.area
    box2_area = box2.area
    union_area = box1_area + box2_area - inter_area

    if union_area == 0:
        if box1_area == 0 and box2_area == 0 and \
           abs(box1.x1 - box2.x1) < FLOAT_COMPARISON_EPSILON and \
           abs(box1.y1 - box2.y1) < FLOAT_COMPARISON_EPSILON and \
           abs(box1.w) < FLOAT_COMPARISON_EPSILON and abs(box1.h) < FLOAT_COMPARISON_EPSILON and \
           abs(box2.w) < FLOAT_COMPARISON_EPSILON and abs(box2.h) < FLOAT_COMPARISON_EPSILON:
            return 1.0
        return 0.0
    return inter_area / union_area
    
def calculate_corrections(before_bboxes_data: list, after_bboxes_data: list) -> list:
    """
    Calculates corrections when 'after' bboxes do not have UUIDs.

    Args:
        before_bboxes_data: List of dicts for 'before' bboxes (must have 'uuid').
                            Expected keys: 'uuid', 'x', 'y', 'w', 'h', 'label'.
        after_bboxes_data: List of dicts for 'after' bboxes (no 'uuid').
                                   Expected keys: 'x', 'y', 'w', 'h', 'label'.
    Returns:
        A list of correction dictionaries.
    """
    
    # Parse 'before' bboxes (they have UUIDs)
    before_bboxes = []
    seen_before_uuids = set()
    for i, b_data in enumerate(before_bboxes_data):
        try:
            b_uuid = b_data['uuid']
            if b_uuid in seen_before_uuids:
                raise ValueError(f"Duplicate UUID '{b_uuid}' found in before_bboxes_data at index {i}.")
            seen_before_uuids.add(b_uuid)
            before_bboxes.append(BoundingBox(
                id_val=b_uuid,
                original_correction_id=b_data.get('original_correction_id'),
                x=b_data['x'],
                y=b_data['y'],
                w=b_data['w'],
                h=b_data['h'],
                label=b_data['label']
            ))
        except KeyError as e:
            raise ValueError(f"Input 'before' bounding box data (index {i}) is missing key: {e}. Data: {b_data}")
        except ValueError as e: # Catch BoundingBox internal errors
             raise ValueError(f"Error processing 'before' bounding box data (index {i}): {e}. Data: {b_data}")


    before_bboxes_map = {bb.uuid: bb for bb in before_bboxes}

    # Parse 'after' bboxes (they do NOT have UUIDs, assign temporary IDs)
    after_boxes_list = []
    for idx, a_data in enumerate(after_bboxes_data):
        try:
            # Assign a temporary ID for internal tracking
            temp_id = f"temp_after_{idx}"
            after_box = BoundingBox(
                x=a_data['x'], y=a_data['y'], w=a_data['w'], 
                h=a_data['h'], label=a_data['label'], id_val=temp_id
            )
            after_boxes_list.append(after_box)
        except KeyError as e:
            raise ValueError(f"Input 'after' bounding box data (index {idx}) is missing key: {e}. Data: {a_data}")
        except ValueError as e: # Catch BoundingBox internal errors
             raise ValueError(f"Error processing 'after' bounding box data (index {idx}): {e}. Data: {a_data}")


    unmatched_before_ids = set(before_bboxes_map.keys())
    # Keep track of 'after' boxes that have been matched using their temporary IDs
    available_after_temp_ids = {ab.uuid for ab in after_boxes_list} # Set of "temp_after_{idx}"

    corrections = []

    # Step 1: Create all possible matches between 'before' and 'after' boxes
    possible_matches = []
    for b_before in before_bboxes_map.values():
        for b_after in after_boxes_list: 
            iou = calculate_iou(b_before, b_after)
            if iou >= IOU_THRESHOLD:
                possible_matches.append({
                    'before_uuid': b_before.uuid, 
                    'after_temp_id': b_after.uuid, # This is "temp_after_{idx}"
                    'iou': iou,
                    'before_box_obj': b_before, # Keep direct references
                    'after_box_obj': b_after
                })

    # Sort matches by IoU in descending order to prioritize best matches
    possible_matches.sort(key=lambda x: x['iou'], reverse=True)

    # Step 2: Process sorted matches to make one-to-one assignments
    for match in possible_matches:
        before_id = match['before_uuid']
        after_temp_id = match['after_temp_id']

        if before_id in unmatched_before_ids and after_temp_id in available_after_temp_ids:
            b_before = match['before_box_obj']
            b_after = match['after_box_obj']
            match_iou = match['iou']

            label_changed = b_before.label != b_after.label
            coords_changed = match_iou < 1.0 - FLOAT_COMPARISON_EPSILON

            # If both label and coords change, two separate correction entries are made
            # for the same original_bbox_uuid, referencing the same final_bbox_data.
            if label_changed:
                corrections.append({
                    "type": "CHANGED_LABEL",
                    "original_bbox_uuid": b_before.uuid,
                    "original_label": b_before.label,
                    "new_label": b_after.label,
                    "final_bbox_data": { 
                        "coords": b_after.coords_xywh,
                        "label": b_after.label 
                    }
                })
            
            if coords_changed:
                corrections.append({
                    "type": "CHANGED_COORDS",
                    "original_bbox_uuid": b_before.uuid,
                    "original_coords": b_before.coords_xywh,
                    "new_coords": b_after.coords_xywh,
                    "final_bbox_data": {
                        "coords": b_after.coords_xywh,
                        "label": b_after.label 
                    },
                    "iou_with_original": round(match_iou, 4) # For context
                })
            
            unmatched_before_ids.remove(before_id)
            available_after_temp_ids.remove(after_temp_id)

    # Step 3: Identify ADDED_MISSING and REMOVED_EXTRA
    for temp_id in available_after_temp_ids:
        # Find the 'after' box corresponding to this temp_id
        b_added = next((ab for ab in after_boxes_list if ab.uuid == temp_id), None)
        if b_added: # Should always be found
            corrections.append({
                "type": "ADDED_MISSING",
                "added_bbox_data": { # No original UUID for the added box itself
                    "coords": b_added.coords_xywh,
                    "label": b_added.label
                }
            })

    for before_id in unmatched_before_ids:
        b_removed = before_bboxes_map[before_id]
        corrections.append({
            "type": "REMOVED_EXTRA",
            "original_bbox_uuid": b_removed.uuid,
            "removed_bbox_details": {
                "uuid": b_removed.uuid, # UUID of the removed box
                "coords": b_removed.coords_xywh,
                "label": b_removed.label
            }
        })
        
    return corrections

def resolve_original_uuid(correction: dict, previous_corrections: dict):
    while True:
        if correction is None:
            return None
        if correction.get('original_bbox_id') is not None:
            return correction.get('original_bbox_id')
        correction = previous_corrections.get(correction.get('original_correction_id'))

# --- New Function 1: Apply Corrections ---
def apply_corrections(before_bboxes_data_with_uuid: list, corrections: list, previous_corrections: dict = {}) -> list:
    """
    Applies a list of corrections to a 'before' list of bounding boxes to reconstruct
    an 'after' list of bounding boxes (without UUIDs).

    Args:
        before_bboxes_data_with_uuid: List of original bounding box dicts (must include 'uuid').
        corrections: List of correction dicts.

    Returns:
        A list of 'after' bounding box dicts, each with 'coords' and 'label'.
    """
    # Initialize a map representing the state of boxes that originated from the 'before' list.
    # Key: original_bbox_uuid, Value: {'coords': ..., 'label': ...} data for the 'after' list.
    final_state_map = {}
    for bbox_data in before_bboxes_data_with_uuid:
        try:
            # Store the initial state, stripping the UUID for the value part
            final_state_map[bbox_data['uuid']] = {
                'uuid': bbox_data['uuid'],
                'original_correction_id': bbox_data.get('original_correction_id'),
                'x': bbox_data['x'],
                'y': bbox_data['y'],
                'w': bbox_data['w'],
                'h': bbox_data['h'],
                'label': bbox_data['label']
            }
        except KeyError as e:
            raise ValueError(f"Input 'before' bounding box for apply_corrections is missing key: {e}. Data: {bbox_data}")


    added_boxes_for_after_list = []

    for correction in corrections:
        corr_type = correction.get("type")
        original_uuid = resolve_original_uuid(correction, previous_corrections)
        correction_id = correction.get('id', str(uuid.uuid4()))

        if corr_type == "REMOVED_EXTRA":
            if original_uuid in final_state_map:
                del final_state_map[original_uuid]
        elif corr_type == "ADDED_MISSING":
            added_boxes_for_after_list.append({'uuid': correction_id, 'original_bbox_id': correction_id, 'original_correction_id': correction_id, **copy.deepcopy(correction['added_bbox_data']['coords']), 'label': correction['added_bbox_data']['label']})
        elif corr_type == "CHANGED_COORDS":
            if original_uuid in final_state_map: # Ensure the original box was meant to be there
                # The 'final_bbox_data' in the correction defines the state of this box in the 'after' list
                final_state_map[original_uuid] = { 'uuid': original_uuid, 'original_correction_id': correction_id, **copy.deepcopy(correction['final_bbox_data']['coords']), 'label': final_state_map[original_uuid]['label'] }
            # If original_uuid is not in final_state_map, it implies a correction for a non-existent
            # or already removed box, which might indicate an issue with correction list consistency
            # or that it was removed by a prior REMOVED_EXTRA correction for the same UUID (though unlikely).
            # For now, we assume corrections are consistent.
        elif corr_type == "CHANGED_LABEL":
             if original_uuid in final_state_map: # Ensure the original box was meant to be there
                # The 'final_bbox_data' in the correction defines the state of this box in the 'after' list
                final_state_map[original_uuid]['label'] = correction['final_bbox_data']['label']
                final_state_map[original_uuid]['original_correction_id'] = correction_id

    reconstructed_after_bboxes = list(final_state_map.values()) + added_boxes_for_after_list
    return reconstructed_after_bboxes

def compare_after_lists(
    after_list_A_no_uuid: list, 
    after_list_B_no_uuid: list, 
    comparison_iou_threshold: float = IOU_THRESHOLD # Default to global IOU_THRESHOLD
) -> bool:
    """
    Compares two lists of 'after' bounding boxes (which do not have UUIDs).
    Returns True if the lists are considered different, False if they are the same.
    Sameness is determined by finding a one-to-one mapping where each pair
    has IoU >= comparison_iou_threshold and identical labels.

    Args:
        after_list_A_no_uuid: List of bbox dicts ({'coords':..., 'label':...}).
        after_list_B_no_uuid: Another list of bbox dicts.
        comparison_iou_threshold: The IoU threshold for considering boxes matched.

    Returns:
        bool: True if different, False if same.
    """
    if len(after_list_A_no_uuid) != len(after_list_B_no_uuid):
        return True # Different number of boxes

    if not after_list_A_no_uuid: # Both are empty if lengths matched
        return False # Same (both empty)

    try:
        bboxes_A = [
            BoundingBox(id_val=f"A_{i}", x=item['x'], y=item['y'], w=item['w'], h=item['h'], label=item['label']) 
            for i, item in enumerate(after_list_A_no_uuid)
        ]
        bboxes_B = [
            BoundingBox(id_val=f"B_{i}", x=item['x'], y=item['y'], w=item['w'], h=item['h'], label=item['label'])
            for i, item in enumerate(after_list_B_no_uuid)
        ]
    except (KeyError, TypeError) as e:
        # This indicates malformed input lists
        raise ValueError(f"Malformed item in 'after' list for comparison: {e}")


    num_boxes = len(bboxes_A)
    matched_A_indices = set()
    matched_B_indices = set()
    num_matches_found = 0

    possible_pairs = []
    for i, box_a in enumerate(bboxes_A):
        for j, box_b in enumerate(bboxes_B):
            iou = calculate_iou(box_a, box_b)
            if iou >= comparison_iou_threshold and box_a.label == box_b.label:
                possible_pairs.append({'iou': iou, 'idx_a': i, 'idx_b': j})
    
    # Sort by IoU descending to prioritize best matches
    possible_pairs.sort(key=lambda x: x['iou'], reverse=True)

    for pair in possible_pairs:
        idx_a = pair['idx_a']
        idx_b = pair['idx_b']
        if idx_a not in matched_A_indices and idx_b not in matched_B_indices:
            matched_A_indices.add(idx_a)
            matched_B_indices.add(idx_b)
            num_matches_found += 1
            if num_matches_found == num_boxes: # Optimization: if all found, no need to check more
                break 
    
    return num_matches_found != num_boxes

def run_corrections_calculation_on_one_image(image: Image, roboflow_image: ImageSplitInput):
    before_bboxes = list(map(lambda e: { 'uuid': e.id, 'x': e.x1, 'y': e.y1, 'w': e.x2 - e.x1, 'h': e.y2 - e.y1, 'label': e.label }, image.bboxes))
    after_bboxes = list(map(lambda e: 
            {                 
                'x': max(0, round((e.center_x - e.width / 2) * roboflow_image.image_width)),
                'y': max(0, round((e.center_y - e.height / 2) * roboflow_image.image_height)),
                'w': round(e.width * roboflow_image.image_width),
                'h': round(e.height * roboflow_image.image_height),
                'label': e.label
            },
            filter(lambda e: e.height > 0 and e.width > 0, roboflow_image.bboxes)
        )
    )
    image.imageInVerificationSession.sort(key=lambda e: e.verificationSession.timeAssigned.timestamp())
    for imageInVerificationSession in image.imageInVerificationSession:
        before_bboxes = apply_corrections(before_bboxes, list(map(lambda e: model_to_correction(e), imageInVerificationSession.corrections)))
    corrections = calculate_corrections(before_bboxes, after_bboxes)
    use_existing_verification_session = len(image.imageInVerificationSession) > 0 and image.imageStatus == ImageStatus.VERIFICATION_IN_PROGRESS and len(image.imageInVerificationSession[-1].corrections) == 0
    verification_session_id = image.imageInVerificationSession[-1].verificationSessionId if use_existing_verification_session else None
    return image, list(map(lambda e: correction_to_model(image.id, e, verification_session_id=verification_session_id), corrections)), verification_session_id

def generate_image_with_bounding_boxes(boxes, image_path, output_path, image_size=(1920, 1080), background_color=(0, 0, 0), box_color=(255, 0, 0), box_thickness=2):
    """
    Generates an image with bounding boxes drawn on it.

    Args:
        boxes: A list of dictionaries, where each dictionary represents a bounding box
               and has the keys 'x', 'y', 'w', 'h', and 'label'.
        image_size: A tuple (width, height) representing the size of the image to generate.
        background_color: A tuple (R, G, B) representing the background color of the image.
        box_color: A tuple (R, G, B) representing the color of the bounding boxes.
        box_thickness: The thickness of the bounding box lines.

    Returns:
        A PIL Image object with the bounding boxes drawn on it.
    """
    # Create a new image with the specified size and background color
    img = PIL.Image.open(image_path)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(40)

    # Draw each bounding box on the image
    for box in boxes:
        x1 = box['x']
        y1 = box['y']
        x2 = x1 + box['w']
        y2 = y1 + box['h']
        label = box['label']

        # Draw the rectangle
        draw.rectangle([(x1, y1), (x2, y2)], outline=box_color, width=box_thickness)

        # Draw the label.  Try to place it above the box, but if there isn't room,
        # place it below.
        label_y = y1 - 10
        if label_y < 0:
            label_y = y2 + 2
        draw.text((x1 + 10, label_y + 10), label, fill=box_color, font=font)

    img.save(output_path)


if __name__ == '__main__':
    image_id = "000f99a7-ea37-4f5a-8470-3afb3a0e60b4"
    bboxes = [
        ["56e2188a-0eee-47a8-8baa-5a44ce1042c7",   31, 117,  404,  628, "gabletop"],
        ["0b4933f7-11d3-4928-bf70-5ed7aeed5125",  350, 851,  642, 1014, "plastic"],
        ["b3c3e5b7-3784-4c6f-854e-dac53b2f3760",  889, 307, 1028,  544, "can"],
        ["b4d808b6-2c4e-4d0f-8fdc-92f169ba60e1", 1019, 576, 1314, 1004, "plastic"],
        ["501b0a10-f6ab-4d55-8c3c-831418c96759",  785,  63, 1129,  345, "plastic"],
        ["8778910d-ef8c-4b92-aa14-ffaa886825ed", 1595, 822, 1797, 1054, "can"],
        ["94264c8a-3f4b-4350-a1fc-a918f665a3b7", 1666,  30, 1871,  352, "can"],
        ["f5a187bc-f699-40ad-9731-ad28d13c9591",  421, 417,  571,  709, "drinkbox"],
        ["545025d0-1167-40fb-b2dc-61307ea0f773", 1815,  57, 1920,  281, "gabletop"],
        ["b31708ec-4bf5-4d40-ab88-55e09e9160af",  421, 417,  570,  709, "plastic"],
    ]
    corrections = [
        ["32d827e6-8e75-4ecb-bbf5-6dd41242a720", None, None, None, None, "plastic", CorrectionType.CHANGED_LABEL, "8778910d-ef8c-4b92-aa14-ffaa886825ed"],
        ["4e3e4207-f2d5-4289-86c8-0373de1631a2", None, None, None, None, "can"    , CorrectionType.CHANGED_LABEL, "f5a187bc-f699-40ad-9731-ad28d13c9591"],
        ["367123c5-ff62-4c13-ba34-313c6605a895", None, None, None, None, "plastic", CorrectionType.CHANGED_LABEL, "94264c8a-3f4b-4350-a1fc-a918f665a3b7"],
        ["610b09cc-a0e0-4098-9018-0f1f71b032e2", 1668,  30, 1873, 352, None, CorrectionType.CHANGED_COORDS, "94264c8a-3f4b-4350-a1fc-a918f665a3b7"],
        ["45375b72-29f4-4c7b-9f7b-66948588fb07", 1031, 506, 1385, 773, "plastic", CorrectionType.ADDED_MISSING , None],
        ["c9f0846e-2ae1-455f-88d1-64cb2ad05dfd", None, None, None, None, None, CorrectionType.REMOVED_EXTRA, "b31708ec-4bf5-4d40-ab88-55e09e9160af"],
        ["5e70cddc-08ac-43d6-b063-e622f146214a", None, None, None, None, None, CorrectionType.REMOVED_EXTRA, "545025d0-1167-40fb-b2dc-61307ea0f773"],
    ]
    bboxes_parsed = list(map(lambda data: BBox(
            id=data[0],
            x1=data[1],
            y1=data[2],
            x2=data[3],
            y2=data[4],
            label=data[5],
            imageId=image_id
        ), bboxes))
    image = Image(
        id=image_id,
        fileExtension='jpg',
        height=1080,
        width=1920,
        index=0,
        chunkId="",
        batchId="65246224-f4a0-4ad8-a12a-59ff01cd5a60",
        imageStatus=ImageStatus.VERIFIED,
        timeTaken=datetime.now(),
        bboxes=bboxes_parsed,
        imageInVerificationSession=[ImageInVerificationSession(
            verificationSession=VerificationSession(
                id="",
                userId="",
                timeAssigned=datetime.now(),
            ),
            verificationSessionId="5e70cddc-08ac-43d6-b063-e622f146214a",
            imageId=image_id,
            corrections=list(map(lambda data: Correction(
                id=data[0],
                x1=data[1],
                y1=data[2],
                x2=data[3],
                y2=data[4],
                newLabel=data[5],
                correctionType=data[6],
                originalBBoxId=data[7],
                originalBBox=list(filter(lambda e: e.id == data[7], bboxes_parsed))[0] if data[7] is not None else None,
                imageId=image_id
            ), corrections))
        ),
        ImageInVerificationSession(
            verificationSession=VerificationSession(
                id="",
                userId="",
                timeAssigned=datetime.now(),
            ),
            verificationSessionId="5e70cddc-08ac-43d6-b063-e622f146214a",
            imageId=image_id,
            corrections=[
                Correction(
                    id="test",
                    # x1=data[1],
                    # y1=data[2],
                    # x2=data[3],
                    # y2=data[4],
                    newLabel="can",
                    correctionType=CorrectionType.CHANGED_LABEL,
                    # originalBBoxId="45375b72-29f4-4c7b-9f7b-66948588fb07",
                    originalCorrectionId="45375b72-29f4-4c7b-9f7b-66948588fb07",
                    # originalBBoxId=data[7],
                    # originalBBox=list(filter(lambda e: e.id == data[7], bboxes_parsed))[0] if data[7] is not None else None,
                    imageId=image_id
                ),
                Correction(
                    id="test1",
                    # x1=data[1],
                    # y1=data[2],
                    # x2=data[3],
                    # y2=data[4],
                    # newLabel="can",
                    correctionType=CorrectionType.REMOVED_EXTRA,
                    # originalBBoxId="45375b72-29f4-4c7b-9f7b-66948588fb07",
                    originalCorrectionId="610b09cc-a0e0-4098-9018-0f1f71b032e2",
                    # originalBBoxId=data[7],
                    # originalBBox=list(filter(lambda e: e.id == data[7], bboxes_parsed))[0] if data[7] is not None else None,
                    imageId=image_id
                ),
                Correction(
                    id="test2",
                    x1=1600,
                    y1=30,
                    x2=1900,
                    y2=352,
                    # newLabel="can",
                    correctionType=CorrectionType.CHANGED_COORDS,
                    # originalBBoxId="45375b72-29f4-4c7b-9f7b-66948588fb07",
                    originalCorrectionId="367123c5-ff62-4c13-ba34-313c6605a895",
                    # originalBBoxId=data[7],
                    # originalBBox=list(filter(lambda e: e.id == data[7], bboxes_parsed))[0] if data[7] is not None else None,
                    imageId=image_id
                )
            ]
        )
        ]
    )
    # roboflow_image = ImageSplitInput(
    #     roboflowFileName=f'{image_id}.jpg'
    # )

    before_bboxes = list(map(lambda e: { 'uuid': e.id, 'x': e.x1, 'y': e.y1, 'w': e.x2 - e.x1, 'h': e.y2 - e.y1, 'label': e.label }, image.bboxes))
    corrections = list(map(lambda e: model_to_correction(e), image.imageInVerificationSession[0].corrections))
    after = apply_corrections(before_bboxes, corrections)
    generate_image_with_bounding_boxes(before_bboxes, "000f99a7-ea37-4f5a-8470-3afb3a0e60b4.jpg", 'before.jpg')
    generate_image_with_bounding_boxes(after, "000f99a7-ea37-4f5a-8470-3afb3a0e60b4.jpg", 'after_1.jpg')
    corrections_1 = list(map(lambda e: model_to_correction(e), image.imageInVerificationSession[1].corrections))
    after_2 = apply_corrections(after, corrections_1, previous_corrections={correction['id']: correction for correction in corrections})
    generate_image_with_bounding_boxes(after_2, "000f99a7-ea37-4f5a-8470-3afb3a0e60b4.jpg", 'after_2.jpg')
