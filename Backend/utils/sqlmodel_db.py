from sqlmodel import Field, SQLModel, create_engine, Session, select, update, text, Relationship
from sqlalchemy.orm import joinedload
import datetime
import uuid
import os
import cv2
from dataclasses import dataclass
from supervision import Detections
import numpy as np
from multiprocessing import shared_memory
import requests
from utils.receipt_printer import print_receipt


DATABASE_PATH = 'resources/state.db'
engine = create_engine(f"sqlite:///{DATABASE_PATH}")


class Batch(SQLModel, table=True):
    __tablename__ = "batch"
    
    id: str = Field(primary_key=True)
    express_qr_code: str | None = Field(default=None)
    eazy_pickup_id: int | None = Field(default=None)
    area_collected: str | None = Field(default=None)
    time_started: datetime.datetime
    time_submitted: datetime.datetime | None = Field(default=None)
    count: int
    can_count: int
    plastic_count: int
    drinkbox_count: int
    gabletop_count: int
    pouch_count: int
    expected_count: int | None = Field(default=None)
    expected_can_count: int | None = Field(default=None)
    expected_plastic_count: int | None = Field(default=None)
    expected_drinkbox_count: int | None = Field(default=None)
    expected_gabletop_count: int | None = Field(default=None)
    expected_pouch_count: int | None = Field(default=None)
    yolo_model: str
    category_model: str
    uploaded_to_cdc: bool = Field(default=False)
    compressed_annotated_video: bool = Field(default=False)
    compressed_raw_video: bool = Field(default=False)
    uploaded_annotated_video_to_s3: bool = Field(default=False)
    uploaded_raw_video_to_s3: bool = Field(default=False)
    uploaded_to_counti_dashboard: bool = Field(default=False)
    deleted_videos_locally: bool = Field(default=False)
    deleted_images_locally: bool = Field(default=False)
    multi_container_images: list["MultiContainerImage"] = Relationship(back_populates="batch")
    single_container_images: list["SingleContainerImage"] = Relationship(back_populates="batch")


class MultiContainerImage(SQLModel, table=True):
    __tablename__ = "multicontainerimage"
    
    id: str = Field(primary_key=True)
    height: int
    width: int
    index: int
    time_collected: datetime.datetime
    batch_id: str = Field(foreign_key="batch.id")
    uploaded_to_s3: bool = Field(default=False)
    bboxes: list["BBox"] = Relationship(back_populates="image")
    batch: Batch = Relationship(back_populates="multi_container_images")


class BBox(SQLModel, table=True):
    __tablename__ = "bbox"
    
    id: str = Field(primary_key=True)
    x1: int
    y1: int
    x2: int
    y2: int
    tracker_id: int
    image_id: str = Field(foreign_key="multicontainerimage.id")
    image: MultiContainerImage = Relationship(back_populates="bboxes")


class SingleContainerImage(SQLModel, table=True):
    __tablename__ = "singlecontainerimage"
    
    id: str = Field(primary_key=True)
    height: int
    width: int
    time_collected: datetime.datetime
    predicted_category: str
    tracker_id: int
    batch_id: str = Field(foreign_key="batch.id")
    batch: Batch = Relationship(back_populates="single_container_images")

class CameraSetting(SQLModel, table=True):
    __tablename__ = "camerasetting"
    
    id: str = Field(primary_key=True)
    value: int
    step: int | None = Field(default=None)
    max: int
    min: int



@dataclass
class MultiContainerImageToSave:
    detections: Detections
    image: MultiContainerImage

@dataclass
class DataToSave:
    multi_container_images_to_save: list[MultiContainerImageToSave] | None = None
    single_container_images: list[SingleContainerImage] | None = None
    batch: Batch | None = None
    batch_submitted: bool = False

@dataclass
class TodaySummary:
    num_of_batches: int
    count: int
    can_count: int
    plastic_count: int
    drinkbox_count: int
    gabletop_count: int
    pouch_count: int
    num_of_batches_with_expected: int
    count_accuracy: float
    can_accuracy: float
    plastic_accuracy: float
    drinkbox_accuracy: float
    gabletop_accuracy: float
    pouch_accuracy: float


def init_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.exec(text('PRAGMA foreign_keys = ON;'))
        # camera_settings = [
        #     CameraSetting(
        #         id='brightness',
        #         max=15,
        #         min=-15,
        #         step=1,
        #         value=0
        #     ),
        #     CameraSetting(
        #         id='contrast',
        #         max=30,
        #         min=0,
        #         step=1,
        #         value=9
        #     ),
        #     CameraSetting(
        #         id='saturation',
        #         max=40,
        #         min=0,
        #         step=1,
        #         value=16
        #     ),
        #     CameraSetting(
        #         id='white_balance_automatic',
        #         max=1,
        #         min=0,
        #         value=1
        #     ),
        #     CameraSetting(
        #         id='gamma',
        #         max=500,
        #         min=40,
        #         step=1,
        #         value=220
        #     ),
        #     CameraSetting(
        #         id='gain',
        #         max=40,
        #         min=1,
        #         step=1,
        #         value=7,
        #     ),
        #     CameraSetting(
        #         id='power_line_frequency',
        #         max=2,
        #         min=0,
        #         step=1,
        #         value=0,
        #     ),
        #     CameraSetting(
        #         id='white_balance_temperature',
        #         max=10000,
        #         min=1000,
        #         step=50,
        #         value=4500,
        #     ),
        #     CameraSetting(
        #         id='sharpness',
        #         max=127,
        #         min=0,
        #         step=1,
        #         value=16,
        #     ),
        #     CameraSetting(
        #         id='auto_exposure',
        #         max=1,
        #         min=0,
        #         step=1,
        #         value=1,
        #     ),
        #     CameraSetting(
        #         id='exposure_time_absolute',
        #         max=10000,
        #         min=0,
        #         step=1,
        #         value=70,
        #     ),
        # ]
        # session.add_all(camera_settings)
        session.commit()

def get_camera_settings():
    with Session(engine) as session:
        return list(session.exec(select(CameraSetting)).all())
    
def update_camera_setting(setting_id: str, new_value: int):
    with Session(engine) as session:
        all_settings = list(session.exec(select(CameraSetting)).all())
        setting_index = -1
        for index, setting in all_settings:
            if setting == setting_id:
                setting_index = index
                break
        setting = all_settings[setting_index]
        setting.value = new_value
        session.merge(setting)
        session.commit()
        return get_camera_settings_gstreamer(all_settings)

    
def get_camera_settings_gstreamer(settings: list[CameraSetting] = None):
    if settings is None:
        settings = get_camera_settings()
    rv = 'c,'
    num_settings = len(settings)
    for index, setting in enumerate(settings):
        rv += f'{setting.id}={setting.value}'
        if index != num_settings - 1:
            rv += ','
    return rv


def get_all_batches_from_day(day: datetime.datetime):
    start = datetime.datetime(day.year, day.month, day.day)
    end = start + datetime.timedelta(days=1)

    with Session(engine) as session:
        statement = select(Batch).where(
            (Batch.time_submitted > start) & 
            (Batch.time_submitted < end)
        ).order_by(Batch.time_submitted.desc())
        batches = session.exec(statement).all()
        return list(batches)


def compute_accuracy(actual: int, expected: int):
    return 100.0 - (abs(expected - actual) / expected * 100.0)


def get_today_summary():
    now = datetime.datetime.now()
    start = datetime.datetime(now.year, now.month, now.day)
    return get_day_summary(start, now)


def get_day_summary(start: datetime.datetime, end: datetime.datetime):
    with Session(engine) as session:
        query = text('''
            SELECT 
                count(id) as num_of_batches,
                sum(count),
                sum(can_count),
                sum(plastic_count),
                sum(drinkbox_count),
                sum(gabletop_count),
                sum(pouch_count),
                count(expected_count) as num_of_batches_with_expected,
                avg(1.0 - (abs((count * 1.0) - (expected_count * 1.0))/(expected_count * 1.0)))*100.0 as overallaccuracy,
                avg(1.0 - (abs((can_count * 1.0) - (expected_can_count * 1.0))/(expected_can_count * 1.0)))*100.0 as canaccuracy,
                avg(1.0 - (abs((plastic_count * 1.0) - (expected_plastic_count * 1.0))/(expected_plastic_count * 1.0)))*100.0 as plasticaccuracy,
                avg(1.0 - (abs((drinkbox_count * 1.0) - (expected_drinkbox_count * 1.0))/(expected_drinkbox_count * 1.0)))*100.0 as drinkboxaccuracy,
                avg(1.0 - (abs((gabletop_count * 1.0) - (expected_gabletop_count * 1.0))/(expected_gabletop_count * 1.0)))*100.0 as gabletopaccuracy,
                avg(1.0 - (abs((pouch_count * 1.0) - (expected_pouch_count * 1.0))/(expected_pouch_count * 1.0)))*100.0 as pouchaccuracy 
            FROM batch
            WHERE time_submitted IS NOT NULL 
                AND unixepoch(time_started) > :start_ts 
                AND unixepoch(time_started) < :end_ts
        ''')
        
        result = session.exec(query, params={
            'start_ts': int(start.timestamp()),
            'end_ts': int(end.timestamp())
        }).first()
        
        if not result:
            result = [0] * 14

        return TodaySummary(
            num_of_batches=result[0] if result[0] is not None else 0,
            count=result[1] if result[1] is not None else 0,
            can_count=result[2] if result[2] is not None else 0,
            plastic_count=result[3] if result[3] is not None else 0,
            drinkbox_count=result[4] if result[4] is not None else 0,
            gabletop_count=result[5] if result[5] is not None else 0,
            pouch_count=result[6] if result[6] is not None else 0,
            num_of_batches_with_expected=result[7] if result[7] is not None else 0,
            count_accuracy=result[8],
            can_accuracy=result[9],
            plastic_accuracy=result[10],
            drinkbox_accuracy=result[11],
            gabletop_accuracy=result[12],
            pouch_accuracy=result[13]
        )


def save_state(data_to_save: DataToSave, collected_images_dir: str):
    batch_dirs_created = set()
    shms: list[shared_memory.SharedMemory] = []

    try:
        # Save images to disk
        for image_to_save in data_to_save.multi_container_images_to_save or []:
            image = image_to_save.image
            if str(image.batch_id) not in batch_dirs_created:
                os.makedirs(f'{collected_images_dir}/{image.batch_id}/multi_container_images', exist_ok=True)
                os.makedirs(f'{collected_images_dir}/{image.batch_id}/single_container_images', exist_ok=True)
                batch_dirs_created.add(str(image.batch_id))
            shm = shared_memory.SharedMemory(name=str(image.id), track=False)
            shms.append(shm)
            decoded_frame = np.ndarray((image.height, image.width, 3), np.uint8, buffer=shm.buf)
            cv2.imwrite(f'{collected_images_dir}/{image.batch_id}/multi_container_images/{image.id}.{image.index}.jpg', decoded_frame)

        for image in data_to_save.single_container_images or []:
            if str(image.batch_id) not in batch_dirs_created:
                os.makedirs(f'{collected_images_dir}/{image.batch_id}/multi_container_images', exist_ok=True)
                os.makedirs(f'{collected_images_dir}/{image.batch_id}/single_container_images', exist_ok=True)
                batch_dirs_created.add(str(image.batch_id))
            shm = shared_memory.SharedMemory(name=str(image.id), track=False)
            shms.append(shm)
            decoded_frame = np.ndarray((image.height, image.width, 3), np.uint8, buffer=shm.buf)
            cv2.imwrite(f'{collected_images_dir}/{image.batch_id}/single_container_images/{image.id}.{image.predicted_category}.jpg', decoded_frame)

        # Save to database
        with Session(engine) as session:
            if data_to_save.batch is not None:
                # Try to merge (upsert) the batch
                session.merge(data_to_save.batch)
                print(f'BATCH TO SAVE UPDATE: {data_to_save.batch.id}')

            multi_container_images = list(map(lambda e: e.image, data_to_save.multi_container_images_to_save))

            # Bulk create bboxes
            bboxes = []
            for multi_container_image_to_save in (data_to_save.multi_container_images_to_save or []):
                current_image_bboxes = [
                    BBox(
                        id=str(uuid.uuid4()),
                        x1=int(bbox[0]),
                        y1=int(bbox[1]),
                        x2=int(bbox[2]),
                        y2=int(bbox[3]),
                        tracker_id=int(tracker_id),
                        image_id=str(multi_container_image_to_save.image.id)
                    )
                    for bbox, tracker_id in zip(multi_container_image_to_save.detections.xyxy, multi_container_image_to_save.detections.tracker_id)
                ]
                bboxes.extend(current_image_bboxes)

            # Add all entities
            session.add_all(multi_container_images)
            session.commit()
            session.add_all(bboxes)
            session.add_all(data_to_save.single_container_images)

            if data_to_save.batch_submitted:
                batch = data_to_save.batch
                COUNTI_TOKEN = "eft373HZsZ2XAVfsFdnGhYSy9q4LiFwYCy2EVobOdkksKDUUeQ8kmzBimOjtR5mj"
                API_URL = 'https://counti.recyclorobo.ai/api/store-batch'
                start_time = data_to_save.batch.time_started.astimezone(datetime.timezone.utc)
                end_time = data_to_save.batch.time_submitted.astimezone(datetime.timezone.utc)
                
                response = requests.post(
                    API_URL,
                    headers={"X-Counti-Token": COUNTI_TOKEN},
                    json={
                        'uuid': str(batch.id),
                        'identifier': batch.eazy_pickup_id if batch.eazy_pickup_id is not None else batch.express_qr_code,
                        'type': 'Eazy Pickup' if batch.eazy_pickup_id is not None else 'Express' if batch.express_qr_code is not None else 'Audit',
                        'total_count': batch.count,
                        'count_data': {
                            'can': batch.can_count,
                            'plastic': batch.plastic_count,
                            'gabletop': batch.gabletop_count,
                            'drinkbox': batch.drinkbox_count,
                            'pouch': batch.pouch_count
                        },
                        'start_time': start_time.strftime("%Y-%m-%d %H:%M:%S"),
                        'end_time': end_time.strftime("%Y-%m-%d %H:%M:%S"),
                        'video_s3_object_key': f'counti-videos/{batch.id}/annotated.mp4',
                        'authorized_user_id': 1,
                    },
                    timeout=15
                )
                response_data = response.json()
                print(f'COUNTI DASHBOARD RESPONSE: {response_data}')
                batch.uploaded_to_counti_dashboard = True
                session.merge(batch)

            session.commit()

            if data_to_save.batch_submitted:
                print_receipt(
                    transaction_id=batch.eazy_pickup_id if batch.eazy_pickup_id is not None else batch.express_qr_code,
                    transaction_type='Eazy Pickup' if batch.eazy_pickup_id is not None else 'Express' if batch.express_qr_code is not None else 'Audit',
                    categories={
                        'can': batch.can_count,
                        'plastic': batch.plastic_count,
                        'gabletop': batch.gabletop_count,
                        'drinkbox': batch.drinkbox_count,
                        'pouch': batch.pouch_count
                    },
                    printer_name='EPSON_TM-T20II'
                )

    finally:
        for shm in shms:
            shm.close()


def get_batch_by_id(batch_id: str) -> Batch | None:
    """Get batch by ID for compatibility with peewee's Batch.get_by_id()"""
    with Session(engine) as session:
        statement = select(Batch).where(Batch.id == batch_id)
        return session.exec(statement).first()


def batch_to_dict(batch: Batch, include_relations: bool = False) -> dict:
    """Convert batch to dict for compatibility with peewee's model_to_dict()"""
    if batch is None:
        return None
    
    batch_dict = {
        'id': batch.id,
        'express_qr_code': batch.express_qr_code,
        'eazy_pickup_id': batch.eazy_pickup_id,
        'area_collected': batch.area_collected,
        'time_started': batch.time_started,
        'time_submitted': batch.time_submitted,
        'count': batch.count,
        'can_count': batch.can_count,
        'plastic_count': batch.plastic_count,
        'drinkbox_count': batch.drinkbox_count,
        'gabletop_count': batch.gabletop_count,
        'pouch_count': batch.pouch_count,
        'expected_count': batch.expected_count,
        'expected_can_count': batch.expected_can_count,
        'expected_plastic_count': batch.expected_plastic_count,
        'expected_drinkbox_count': batch.expected_drinkbox_count,
        'expected_gabletop_count': batch.expected_gabletop_count,
        'expected_pouch_count': batch.expected_pouch_count,
        'yolo_model': batch.yolo_model,
        'category_model': batch.category_model,
        'uploaded_to_cdc': batch.uploaded_to_cdc,
        'compressed_annotated_video': batch.compressed_annotated_video,
        'compressed_raw_video': batch.compressed_raw_video,
        'uploaded_annotated_video_to_s3': batch.uploaded_annotated_video_to_s3,
        'uploaded_raw_video_to_s3': batch.uploaded_raw_video_to_s3,
        'uploaded_to_counti_dashboard': batch.uploaded_to_counti_dashboard,
        'deleted_videos_locally': batch.deleted_videos_locally,
        'deleted_images_locally': batch.deleted_images_locally,
    }
    
    if include_relations:
        # Add related data if needed
        with Session(engine) as session:
            # Get multi container images
            multi_images_stmt = select(MultiContainerImage).where(MultiContainerImage.batch_id == batch.id).options(joinedload(MultiContainerImage.bboxes))
            multi_images = session.exec(multi_images_stmt).unique().all()
            batch_dict['multiContainerImages'] = [
                {
                    'id': img.id,
                    'height': img.height,
                    'width': img.width,
                    'index': img.index,
                    'time_collected': img.time_collected,
                    'batch_id': img.batch_id,
                    'uploaded_to_s3': img.uploaded_to_s3,
                    'bboxes': list(map(lambda e: e.model_dump(), img.bboxes))
                }
                for img in multi_images
            ]
            
            # Get single container images
            single_images_stmt = select(SingleContainerImage).where(SingleContainerImage.batch_id == batch.id)
            single_images = session.exec(single_images_stmt).all()
            batch_dict['singleContainerImages'] = [
                {
                    'id': img.id,
                    'height': img.height,
                    'width': img.width,
                    'time_collected': img.time_collected,
                    'predicted_category': img.predicted_category,
                    'tracker_id': img.tracker_id,
                    'batch_id': img.batch_id,
                }
                for img in single_images
            ]
    
    return batch_dict