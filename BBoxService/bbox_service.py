from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Tuple, Optional, Dict
import base64
import cv2  # OpenCV for image decoding
import numpy as np
import asyncio
# from concurrent.futures import ThreadPoolExecutor # Not explicitly needed, FastAPI uses its own
import os
import queue # For the model pool
import sys
from time import perf_counter

# --- Ultralytics YOLO ---
# Ensure you have ultralytics and its dependencies (like torch) installed
# pip install ultralytics
try:
    from ultralytics import YOLO
except ImportError:
    print("Ultralytics YOLO library not found. Please install it: pip install ultralytics")
    sys.exit(-1)

# --- 1. Pydantic Models ---
class ImageInput(BaseModel):
    images_base64: List[str] = Field(..., description="A list of base64 encoded JPEG image strings.")

class BoundingBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    class_id: int
    class_name: str

class PredictionResult(BaseModel):
    image_index: int
    boxes: List[BoundingBox]
    error: Optional[str] = None

class PredictionsResponse(BaseModel):
    results: List[PredictionResult]

# --- 2. YOLOv8 Model Pool Management ---
model_queue: Optional[queue.Queue] = None
yolo_class_names: Dict[int, str] = {}
YOLO_MODEL_NAME = "mdc-counti-container-2025-04-27.pt"

def initialize_model_pool():
    """Initializes the YOLOv8 model pool. Called at startup."""
    global model_queue, yolo_class_names, YOLO

    if YOLO is None:
        print("FATAL: Ultralytics YOLO library is not available. Cannot initialize model pool.")
        model_queue = None
        return

    num_models = os.cpu_count() or 2
    print(f"Attempting to initialize model pool with {num_models} YOLOv8 ('{YOLO_MODEL_NAME}') instances...")
    current_model_queue = queue.Queue(maxsize=num_models)

    try:
        print(f"Loading initial YOLOv8 model instance ('{YOLO_MODEL_NAME}')...")
        temp_model = YOLO(YOLO_MODEL_NAME)
        _ = temp_model.predict(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False) # Warm-up
        
        yolo_class_names = temp_model.names
        current_model_queue.put(temp_model)
        print(f"Successfully loaded initial model. Class names: {yolo_class_names}")

        for i in range(num_models - 1):
            print(f"Loading YOLOv8 model instance {i+2}/{num_models}...")
            model = YOLO(YOLO_MODEL_NAME)
            _ = model.predict(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False) # Warm-up
            current_model_queue.put(model)
        
        model_queue = current_model_queue
        print(f"YOLOv8 model pool initialized successfully with {model_queue.qsize()} models.")

    except Exception as e:
        print(f"FATAL: Error loading YOLOv8 model or initializing pool: {e}")
        print("Ensure you have the model file (e.g., 'yolov8n.pt') accessible or an internet connection for auto-download.")
        model_queue = None

# --- 3. FastAPI Application Setup ---
app = FastAPI(
    title="YOLOv8 Bounding Box Prediction API",
    description="An API to detect objects in images using a YOLOv8 model pool. Workers block if pool is empty.",
    version="0.2.1" # Incremented version
)

@app.on_event("startup")
async def startup_event():
    """Load the model pool when the application starts."""
    print("Application startup: Initializing YOLOv8 model pool...")
    initialize_model_pool()
    if model_queue is None: # Simplified check: None means failure.
        print("CRITICAL: YOLOv8 model pool could not be initialized. The /predict/ endpoint will return errors.")
    elif model_queue.empty(): # Pool initialized but somehow empty (should not happen with current logic)
         print("Warning: YOLOv8 model pool is initialized but empty. This is unexpected. Predictions will block indefinitely.")
    else:
        print(f"YOLOv8 model pool ready with {model_queue.qsize()} models.")


# --- 4. Image Processing and Prediction Function ---
def process_single_image(image_idx: int, image_base64_str: str) -> PredictionResult:
    """
    Decodes a single base64 image, runs YOLOv8 prediction using a model from the pool,
    and formats the result. This function will block if the model_queue is empty.
    """
    global model_queue, yolo_class_names

    # This check should ideally not be hit if the endpoint guards against model_queue being None.
    # However, it's a safe fallback.
    if model_queue is None:
        return PredictionResult(image_index=image_idx, boxes=[], error="YOLOv8 model pool not initialized on server.")

    model_instance: Optional[YOLO] = None
    try:
        # Step 0: Get a model from the pool.
        # This call will block indefinitely if the queue is empty until a model is available.
        # 'block=True' is the default behavior for get() when no timeout is specified.
        print(f"Image {image_idx}: Attempting to get model from queue (size: {model_queue.qsize()})...")
        model_instance = model_queue.get(block=True)
        print(f"Image {image_idx}: Model acquired. Proceeding with processing. Queue size now: {model_queue.qsize()}")


        # Step 1: Decode Base64 String
        try:
            image_bytes = base64.b64decode(image_base64_str)
        except Exception as e:
            # If decoding fails, we must still return the model to the queue.
            return PredictionResult(image_index=image_idx, boxes=[], error=f"Invalid base64 string: {str(e)}")

        # Step 2: Convert Bytes to OpenCV Image (NumPy array)
        image_np_array = np.frombuffer(image_bytes, np.uint8)
        img_cv2 = cv2.imdecode(image_np_array, cv2.IMREAD_COLOR)

        if img_cv2 is None:
            return PredictionResult(image_index=image_idx, boxes=[], error="Failed to decode image. Invalid image format or corrupt data.")

        # Step 3: Perform Prediction using the acquired YOLOv8 model instance
        results = model_instance.predict(img_cv2, verbose=False)

        # Step 4: Format Results
        formatted_bounding_boxes = []
        if results and len(results) > 0:
            result_data = results[0]
            boxes_xyxy = result_data.boxes.xyxy.cpu().numpy()
            confidences = result_data.boxes.conf.cpu().numpy()
            class_ids_tensor = result_data.boxes.cls.cpu().numpy()

            for i in range(len(boxes_xyxy)):
                x1, y1, x2, y2 = boxes_xyxy[i]
                confidence = float(confidences[i])
                class_id = int(class_ids_tensor[i])
                class_name = yolo_class_names.get(class_id, "unknown_class")

                formatted_bounding_boxes.append(
                    BoundingBox(
                        x1=int(x1),
                        y1=int(y1),
                        x2=int(x2),
                        y2=int(y2),
                        confidence=confidence,
                        class_id=class_id,
                        class_name=class_name
                    )
                )
        return PredictionResult(image_index=image_idx, boxes=formatted_bounding_boxes)

    except Exception as e:
        # This catches any unexpected errors during the processing of this single image.
        print(f"Error processing image index {image_idx}: {e}")
        # import traceback # For more detailed debugging if needed
        # print(traceback.format_exc())
        return PredictionResult(image_index=image_idx, boxes=[], error=f"Unexpected error processing image: {str(e)}")
    finally:
        # Step 5: Critical - Return the model instance to the queue
        if model_instance and model_queue:
            model_queue.put(model_instance)
            print(f"Image {image_idx}: Model returned to queue. Queue size now: {model_queue.qsize()}")


# --- 5. API Endpoint ---
@app.post("/predict/", response_model=PredictionsResponse)
async def predict_images_bounding_boxes(payload: ImageInput = Body(...)):
    """
    Accepts a list of base64 encoded JPEG images and returns detected bounding boxes.
    Image processing tasks will block if all models in the pool are in use.
    """
    global model_queue
    
    # First, critical check: was the model pool initialized successfully?
    if model_queue is None:
        raise HTTPException(
            status_code=503, 
            detail="YOLOv8 model pool is not available (failed to initialize). Check server logs."
        )

    # Handle requests that contain no images.
    if not payload.images_base64:
        print("Received request with no images.")
        return PredictionsResponse(results=[])

    # At this point, model_queue is initialized and there are images to process.
    # If model_queue happens to be empty (all models are currently in use by other tasks),
    # the new tasks, when they call model_queue.get(), will block until a model is free.
    print(f"Received prediction request for {len(payload.images_base64)} images. Current model queue size: {model_queue.qsize()}")

    loop = asyncio.get_event_loop()
    start = perf_counter()
    tasks = []
    for i, base64_img_str in enumerate(payload.images_base64):
        task = loop.run_in_executor(None, process_single_image, i, base64_img_str)
        tasks.append(task)

    try:
        prediction_results_list: List[PredictionResult] = await asyncio.gather(*tasks)
    except Exception as e:
        # This would typically catch errors from asyncio.gather itself,
        # or if a task raised an unhandled exception not converted to PredictionResult.error
        print(f"Error during asyncio.gather for image predictions: {e}")
        raise HTTPException(status_code=500, detail=f"Error during parallel processing of images: {str(e)}")
    end = perf_counter()

    print(f'{len(payload.images_base64)} images took {end - start} seconds')
    return PredictionsResponse(results=prediction_results_list)

# --- 6. Main (for running with Uvicorn) ---
if __name__ == "__main__":
    import uvicorn
    print("Starting Uvicorn server directly. For production, use 'uvicorn main:app --host 0.0.0.0 --port 8000'")
    uvicorn.run(app, host="0.0.0.0", port=8000)
