import uuid # For example UUIDs in the 'before' set for testing
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import tqdm
import copy
import json
from PIL import Image, ImageDraw
from prisma import Prisma
from prisma.enums import BBoxType, CorrectionType
from asyncio import run

# --- Configuration ---
IOU_THRESHOLD = 0.9
# Epsilon for floating point comparisons, e.g., to check if IoU is effectively 1.0
FLOAT_COMPARISON_EPSILON = 1e-7


# --- Helper Classes and Functions ---

correction_counts = {
    'CHANGED_COORDS': 0,
    'CHANGED_LABEL': 0,
    'ADDED_MISSING': 0,
    'REMOVED_EXTRA': 0,
}

class BoundingBox:
    """
    Represents a bounding box with its properties.
    'uuid' can be an original UUID (for 'before' boxes) or a temporary one (for 'after' boxes).
    """
    def __init__(self, x, y, w, h, label, id_val=None): # id_val is the UUID or temporary ID
        self.uuid = str(id_val) if id_val is not None else None # Store ID as string
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

# --- Main Correction Logic ---

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
                id_val=b_uuid, x=b_data['x'], y=b_data['y'],
                w=b_data['w'], h=b_data['h'], label=b_data['label']
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
                correction_counts["CHANGED_LABEL"] += 1
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
                correction_counts["CHANGED_COORDS"] += 1
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
            correction_counts["ADDED_MISSING"] += 1
            corrections.append({
                "type": "ADDED_MISSING",
                "added_bbox_data": { # No original UUID for the added box itself
                    "coords": b_added.coords_xywh,
                    "label": b_added.label
                }
            })

    for before_id in unmatched_before_ids:
        b_removed = before_bboxes_map[before_id]
        correction_counts["REMOVED_EXTRA"] += 1
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

# --- New Function 1: Apply Corrections ---
def apply_corrections(before_bboxes_data_with_uuid: list, corrections: list) -> list:
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
                'x': bbox_data['x'], 'y': bbox_data['y'], 'w': bbox_data['w'], 'h': bbox_data['h'],
                'label': bbox_data['label']
            }
        except KeyError as e:
            raise ValueError(f"Input 'before' bounding box for apply_corrections is missing key: {e}. Data: {bbox_data}")


    added_boxes_for_after_list = []

    for correction in corrections:
        corr_type = correction.get("type")
        original_uuid = correction.get("original_bbox_uuid")

        if corr_type == "REMOVED_EXTRA":
            if original_uuid in final_state_map:
                del final_state_map[original_uuid]
        elif corr_type == "ADDED_MISSING":
            added_boxes_for_after_list.append({**copy.deepcopy(correction['added_bbox_data']['coords']), 'label': correction['added_bbox_data']['label']})
        elif corr_type in ["CHANGED_LABEL", "CHANGED_COORDS"]:
            if original_uuid in final_state_map: # Ensure the original box was meant to be there
                # The 'final_bbox_data' in the correction defines the state of this box in the 'after' list
                final_state_map[original_uuid] = {**copy.deepcopy(correction['final_bbox_data']['coords']), 'label': correction['final_bbox_data']['label']}
            # If original_uuid is not in final_state_map, it implies a correction for a non-existent
            # or already removed box, which might indicate an issue with correction list consistency
            # or that it was removed by a prior REMOVED_EXTRA correction for the same UUID (though unlikely).
            # For now, we assume corrections are consistent.

    reconstructed_after_bboxes = list(final_state_map.values()) + added_boxes_for_after_list
    return reconstructed_after_bboxes


# --- New Function 2: Compare After Lists ---
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

def calculate_iou_dict(box1, box2):
    """
    Calculate the Intersection over Union (IoU) of two bounding boxes.

    Args:
        box1: A dictionary representing the first bounding box with keys 'x', 'y', 'w', and 'h'.
        box2: A dictionary representing the second bounding box with keys 'x', 'y', 'w', and 'h'.

    Returns:
        The IoU of the two bounding boxes.
    """
    x1_intersection = max(box1['x'], box2['x'])
    y1_intersection = max(box1['y'], box2['y'])
    x2_intersection = min(box1['x'] + box1['w'], box2['x'] + box2['w'])
    y2_intersection = min(box1['y'] + box1['h'], box2['y'] + box2['h'])

    intersection_width = max(0, x2_intersection - x1_intersection)
    intersection_height = max(0, y2_intersection - y1_intersection)
    intersection_area = intersection_width * intersection_height

    box1_area = box1['w'] * box1['h']
    box2_area = box2['w'] * box2['h']
    union_area = box1_area + box2_area - intersection_area

    if union_area == 0:
        return 0  # Handle the case where both boxes have zero area
    iou = intersection_area / union_area
    return iou

def compare_bounding_box_lists(list1, list2, iou_threshold=0.99):
    """
    Compare two lists of bounding boxes with labels for identity, considering IoU,
    and handles different ordering of boxes in the lists.

    Args:
        list1: The first list of bounding box dictionaries.
        list2: The second list of bounding box dictionaries.
        iou_threshold: The IoU threshold for considering two bounding boxes as identical.

    Returns:
        True if the lists are identical (same labels and IoU >= threshold for corresponding boxes), False otherwise.
    """
    if len(list1) != len(list2):
        return False

    # Create a copy of list2 to keep track of matched boxes.
    list2_copy = list2[:]
    for box1 in list1:
        best_match_index = -1
        best_iou = -1

        for j, box2 in enumerate(list2_copy):
            if box1['label'] == box2['label']:
                iou = calculate_iou_dict(box1, box2)
                if iou > best_iou:
                    best_iou = iou
                    best_match_index = j

        if best_match_index == -1 or best_iou < iou_threshold:
            return False  # No suitable match found for box1

        # Remove the matched box from list2_copy to prevent re-matching.
        del list2_copy[best_match_index]

    return True


# --- Example Usage ---
def tests():
    uuid_obj1 = str(uuid.uuid4())
    uuid_obj2 = str(uuid.uuid4())
    uuid_obj3 = str(uuid.uuid4())
    
    before_bboxes = [
        {"uuid": uuid_obj1, "x": 10, "y": 10, "w": 50, "h": 50, "label": "cat"},
        {"uuid": uuid_obj2, "x": 70, "y": 70, "w": 30, "h": 30, "label": "dog"},
        {"uuid": uuid_obj3, "x": 100, "y": 100, "w": 20, "h": 20, "label": "bird"}, # Will be removed
        {"uuid": "fish_old", "x": 150, "y": 150, "w": 40, "h": 40, "label": "fish"},
        {"uuid": "mouse_old", "x": 200, "y": 10, "w": 10, "h": 10, "label": "mouse"},
        {"uuid": "y_label_old", "x": 5, "y": 5, "w": 10, "h":10, "label": "Y"}
    ]

    # 'after' bboxes do NOT have 'uuid' field
    after_bboxes = [
        {"x": 10, "y": 10, "w": 50, "h": 50, "label": "kitten"},    # Match uuid_obj1 (label change)
        {"x": 75, "y": 75, "w": 30, "h": 30, "label": "dog"},       # Match uuid_obj2 (coords change)
        # No box corresponding to removed uuid_obj3
        {"x": 152, "y": 152, "w": 40, "h": 40, "label": "goldfish"},# Match "fish_old" (coords & label change)
        {"x": 200, "y": 200, "w": 60, "h": 60, "label": "tree"},    # Added
        {"x": 200, "y": 10, "w": 10, "h": 10, "label": "mouse"},    # Match "mouse_old" (identical data, will be matched, no explicit change reported)
        {"x": 5, "y": 5, "w": 10, "h":10, "label": "X"},           # Match "y_label_old" (label change, coords same)
        {"x":300, "y":300, "w":10, "h":10, "label": "rock"}         # Added
    ]

    print("Before BBoxes (with UUIDs):")
    for bbox_data in before_bboxes:
      print(f"  {BoundingBox(id_val=bbox_data['uuid'], **{k:v for k,v in bbox_data.items() if k!='uuid'})}")

    print("\nAfter BBoxes (no input UUIDs):")
    for i, bbox_data in enumerate(after_bboxes):
      print(f"  (temp_id: temp_after_{i}) {BoundingBox(id_val=f'temp_after_{i}', **bbox_data)}")


    print(f"\nUsing IoU Threshold: {IOU_THRESHOLD}")
    
    try:
        corrections = calculate_corrections(before_bboxes, after_bboxes)
        print("\nCalculated Corrections:")
        if not corrections:
            print("  No corrections found.")
        for i, correction in enumerate(corrections):
            print(f"  Correction {i+1}:")
            for key, value in correction.items():
                if isinstance(value, dict):
                    print(f"    {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"      {sub_key}: {sub_value}")
                else:
                    print(f"    {key}: {value}")
            print("-" * 20)
        calculated_after = apply_corrections(before_bboxes, corrections)
        calculated_after.sort(key=lambda e: hash(str(e)))
        after_bboxes.sort(key=lambda e: hash(str(e)))
        print(after_bboxes)
        print(calculated_after)
        is_after_same = compare_after_lists(after_bboxes, calculated_after)
        print(f'IS AFTER DIFFERENT: {is_after_same}')
    except ValueError as e:
        print(f"\nError calculating corrections: {e}")

    # print("\n--- Test Case: Empty 'before' list (all 'after' are ADDED_MISSING) ---")
    # before_empty = []
    # after_single = [{"x": 10, "y": 10, "w": 10, "h": 10, "label": "A"}]
    # corrections_empty_before = calculate_corrections(before_empty, after_single)
    # print("Corrections (empty before):")
    # for c in corrections_empty_before: print(f"  {c}")
    
    # print("\n--- Test Case: Empty 'after' list (all 'before' are REMOVED_EXTRA) ---")
    # before_single = [{"uuid": "old1", "x": 10, "y": 10, "w": 10, "h": 10, "label": "B"}]
    # after_empty = []
    # corrections_empty_after = calculate_corrections(before_single, after_empty)
    # print("Corrections (empty after):")
    # for c in corrections_empty_after: print(f"  {c}")

    # print("\n--- Test Case: Identical data (before has UUIDs, after doesn't) ---")
    # # Before has UUID, After has same data but no UUID. They should match by IoU=1.0.
    # # If label and coords are same, no specific CHANGED_LABEL/CHANGED_COORDS reported.
    # # The boxes are simply considered "matched" and accounted for.
    # identical_before = [{"uuid": "id1_same", "x": 0, "y": 0, "w": 1, "h": 1, "label": "same"}]
    # identical_after = [{"x": 0, "y": 0, "w": 1, "h": 1, "label": "same"}]
    # corrections_identical = calculate_corrections(identical_before, identical_after)
    # print("Corrections (identical data, after has no UUID):")
    # if not corrections_identical: 
    #     print("  No explicit 'change' corrections found (as expected, they matched).")
    # for c in corrections_identical: print(f"  {c}")

classes = [
    'can',
    'plastic',
    'drinkbox',
    'gabletop',
    'pouch',
    'container'
]

def extract_inputs_from_txt_files(annotation_file: str):
    with open(f'corrections_test_data/auto_annotations/{annotation_file}', 'r') as f:
        auto_annotations_txt = f.read()

    before = []
    for line_index, line in enumerate(auto_annotations_txt.split('\n')):
        if line == '':
            continue
        class_index_str, center_x_str, center_y_str, width_str, height_str = line.split(' ')
        class_index, center_x, center_y, width, height = int(class_index_str), float(center_x_str) * 1920, float(center_y_str) * 1080, float(width_str) * 1920, float(height_str) * 1080
        label, x, y, w, h = classes[class_index], round(center_x - width / 2), round(center_y - height / 2), round(width), round(height)
        if h == 0 or w == 0:
            continue
        before.append({'uuid': str(line_index), 'x': x, 'y': y, 'w': w, 'h': h, 'label': label})
    
    with open(f'corrections_test_data/verified_annotations/{annotation_file}', 'r') as f:
        verified_annotations_txt = f.read()

    after = []
    for line_index, line in enumerate(verified_annotations_txt.split('\n')):
        if line == '':
            continue
        class_index_str, center_x_str, center_y_str, width_str, height_str = line.split(' ')
        class_index, center_x, center_y, width, height = int(class_index_str), float(center_x_str) * 1920, float(center_y_str) * 1080, float(width_str) * 1920, float(height_str) * 1080
        label, x, y, w, h = classes[class_index], round(center_x - width / 2), round(center_y - height / 2), round(width), round(height)
        if h == 0 or w == 0:
            continue
        after.append({'x': x, 'y': y, 'w': w, 'h': h, 'label': label})
    
    return annotation_file, before, after

def run_corrections_calculation_on_one_image(annotation_file: str, before: list, after: list):
    corrections = calculate_corrections(before, after)
    calculated_after = apply_corrections(before, corrections)
    afters_are_same = compare_after_lists(after, calculated_after)
    return annotation_file, corrections, afters_are_same

def run_on_prod_data():
    annotation_files = os.listdir('corrections_test_data/auto_annotations')
    inputs = []
    total_auto_bboxes = 0

    with tqdm.tqdm(total=len(annotation_files), desc='Extracting inputs from annotation files') as pbar:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(extract_inputs_from_txt_files, arg): arg for arg in annotation_files}
            for future in as_completed(futures):
                result = future.result()
                inputs.append(result)
                total_auto_bboxes += len(result[1])
                pbar.update(1)

    outputs = []

    with tqdm.tqdm(total=len(inputs), desc='Calculating corrections') as pbar:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(run_corrections_calculation_on_one_image, *arg): arg for arg in inputs}
            for future in as_completed(futures):
                result = future.result()
                outputs.append(result)
                pbar.update(1)

    images_with_no_change = list(filter(lambda e: len(e[1]) == 0, outputs))
    afters_are_not_same = list(filter(lambda e: e[2], outputs))
    print(f'Num of images with no change: {len(images_with_no_change)}')
    print(f'Num of images with different afters: {len(afters_are_not_same)}')

    if len(afters_are_not_same) > 0:
        with open('afters_not_same.json', 'w') as f:
            json.dump(list(map(lambda e: e[0], afters_are_not_same)), f, indent=4)
    print(f'total auto bboxes: {total_auto_bboxes}')
    print(correction_counts)

    

def check_list_equality(list_1: list[dict], list_2: list[dict]) -> bool:
    if len(list_1) != len(list_2):
        return False
    
    list_1_sorted = list(map(lambda e: dict(sorted(e.items())), list_1))
    list_2_sorted = list(map(lambda e: dict(sorted(e.items())), list_2))
    list_1_sorted.sort(key=lambda e: hash(str(e)))
    list_2_sorted.sort(key=lambda e: hash(str(e)))
    
    for i in range(0, len(list_1)):
        item_1 = list_1[i]
        item_2 = list_2[i]
        if hash(str(item_1)) != hash(str(item_2)):
            print(f'{item_1} does not match {item_2}')
            return False
        
    return True

def check_list_equality_from_corrections(after: list, after_calculated: list) -> bool:
    corrections = calculate_corrections(after_calculated, after)
    return len(corrections) == 0

def generate_image_with_bounding_boxes(boxes, image_size=(1920, 1080), background_color=(0, 0, 0), box_color=(255, 0, 0), box_thickness=2):
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
    img = Image.new("RGB", image_size, background_color)
    draw = ImageDraw.Draw(img)

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
        draw.text((x1, label_y), label, fill=box_color)

    return img

def failing_tests():
    with open("afters_not_same.json", 'r') as f:
        afters_not_same = json.load(f)

    for annotation_file in afters_not_same:
        _, before, after = extract_inputs_from_txt_files(annotation_file)
        corrections = calculate_corrections(before, after)[:-1]
        calculated_after = apply_corrections(before, corrections)

        print(f'is different {compare_after_lists(after, calculated_after)}')

async def run_on_prod_data_from_db():
    db = Prisma(
        http={
            'timeout': None
        },
        auto_register=True
    )

    await db.connect()

    total_auto_bboxes = 0
    total_verified_bboxes = 0

    print(f'getting data from db')
    verified_images = await db.image.find_many(where={ 'bboxes': { 'some': { 'bboxType': BBoxType.ANNOTATION }}}, include={ 'bboxes': True })
    print(f'got {len(verified_images)} verified images from db')

    inputs = []

    for verified_image in verified_images:
        before_bboxes = list(map(lambda e: { 'uuid': e.id, 'x': e.x1, 'y': e.y1, 'w': e.x2 - e.x1, 'h': e.y2 - e.y1, 'label': e.label }, filter(lambda e: e.bboxType == BBoxType.DETECTION and e.y2 > e.y1 and e.x2 > e.x1, verified_image.bboxes)))
        after_bboxes = list(map(lambda e: { 'x': e.x1, 'y': e.y1, 'w': e.x2 - e.x1, 'h': e.y2 - e.y1, 'label': e.label }, filter(lambda e: e.bboxType == BBoxType.ANNOTATION and e.y2 > e.y1 and e.x2 > e.x1, verified_image.bboxes)))
        inputs.append((verified_image.id, before_bboxes, after_bboxes))
        total_auto_bboxes += len(before_bboxes)
        total_verified_bboxes += len(after_bboxes)

    outputs = []

    with tqdm.tqdm(total=len(inputs), desc='Calculating corrections') as pbar:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(run_corrections_calculation_on_one_image, *arg): arg for arg in inputs}
            for future in as_completed(futures):
                result = future.result()
                outputs.append(result)
                pbar.update(1)

    images_with_no_change = list(filter(lambda e: len(e[1]) == 0, outputs))
    afters_are_not_same = list(filter(lambda e: e[2], outputs))
    print(f'Num of images with no change: {len(images_with_no_change)}')
    print(f'Num of images with different afters: {len(afters_are_not_same)}')

    if len(afters_are_not_same) > 0:
        with open('afters_not_same.json', 'w') as f:
            json.dump(list(map(lambda e: e[0], afters_are_not_same)), f, indent=4)
    print(f'total auto bboxes: {total_auto_bboxes}')
    print(correction_counts)

    corrections_to_create = []
    for image_id, corrections, afters_are_same in outputs:
        for correction in corrections:
            correction_to_add = None
            if correction.get('type') == 'REMOVED_EXTRA':
                correction_to_add = {
                    'imageId': image_id,
                    'correctionType': CorrectionType.REMOVED_EXTRA,
                    'originalBBoxId': correction.get("original_bbox_uuid")
                }
            elif correction.get('type') == 'CHANGED_LABEL':
                correction_to_add = {
                    'imageId': image_id,
                    'correctionType': CorrectionType.CHANGED_LABEL,
                    'newLabel': correction.get('new_label'),
                    'originalBBoxId': correction.get("original_bbox_uuid")
                }
            elif correction.get('type') == 'CHANGED_COORDS':
                correction_to_add = {
                    'imageId': image_id,
                    'correctionType': CorrectionType.CHANGED_COORDS,
                    'originalBBoxId': correction.get("original_bbox_uuid"),
                    'x1': correction.get('new_coords').get('x'),
                    'y1': correction.get('new_coords').get('y'),
                    'x2': correction.get('new_coords').get('x') + correction.get('new_coords').get('w'),
                    'y2': correction.get('new_coords').get('y') + correction.get('new_coords').get('h'),
                }
            elif correction.get('type') == 'ADDED_MISSING':
                correction_to_add = {
                    'imageId': image_id,
                    'correctionType': CorrectionType.ADDED_MISSING,
                    'x1': correction.get('added_bbox_data').get('coords').get('x'),
                    'y1': correction.get('added_bbox_data').get('coords').get('y'),
                    'x2': correction.get('added_bbox_data').get('coords').get('x') + correction.get('added_bbox_data').get('coords').get('w'),
                    'y2': correction.get('added_bbox_data').get('coords').get('y') + correction.get('added_bbox_data').get('coords').get('h'),
                }
            corrections_to_create.append(correction_to_add)

    print(f'{len(corrections_to_create)} corrections to create')
    # corrections_created = await db.correction.create_many(data=corrections_to_create, skip_duplicates=True)
    # print(f'{corrections_created} created in db')

    await db.disconnect()


if __name__ == "__main__":
    run(run_on_prod_data_from_db())