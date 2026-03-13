from peewee import *
import datetime
import uuid
import os
import cv2
from dataclasses import dataclass
from supervision import Detections
import numpy as np
from multiprocessing import shared_memory

db = SqliteDatabase('resources/state.db')

@dataclass
class MultiContainerImageToSave:
    index: int
    time: datetime
    detections: Detections
    frame_shape: tuple[int, int, int]
    id: uuid.UUID
    batch_id: uuid.UUID

@dataclass
class SingleContainerImageToSave:
    id: uuid.UUID
    time: datetime.datetime
    detected_class: str
    frame_shape: tuple[int, int, int]
    tracker_id: int
    batch_id: uuid.UUID

@dataclass
class BatchToSave:
    id: uuid.UUID
    time_started: datetime.datetime
    time_submitted: datetime.datetime | None
    count: int
    can_count: int
    plastic_count: int
    drinkbox_count: int
    gabletop_count: int
    pouch_count: int
    expected_count: int | None
    expected_can_count: int | None
    expected_plastic_count: int | None
    expected_drinkbox_count: int | None
    expected_gabletop_count: int | None
    expected_pouch_count: int | None
    yolo_model: str
    category_model: str

    
@dataclass
class DataToSave:
    multi_container_images: list[MultiContainerImageToSave] | None = None
    single_container_images: list[SingleContainerImageToSave] | None = None
    batch: BatchToSave | None = None

class BaseModel(Model):
    class Meta:
        database = db


class Batch(BaseModel):
    id = UUIDField(primary_key=True)
    area_collected = TextField(null=True)
    time_started = DateTimeField()
    time_submitted = DateTimeField(null=True)
    count = IntegerField()
    can_count = IntegerField()
    plastic_count = IntegerField()
    drinkbox_count = IntegerField()
    gabletop_count = IntegerField()
    pouch_count = IntegerField()
    expected_count = IntegerField(null=True)
    expected_can_count = IntegerField(null=True)
    expected_plastic_count = IntegerField(null=True)
    expected_drinkbox_count = IntegerField(null=True)
    expected_gabletop_count = IntegerField(null=True)
    expected_pouch_count = IntegerField(null=True)
    yolo_model = TextField()
    category_model = TextField()


class MultiContainerImage(BaseModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4())
    height = IntegerField()
    width = IntegerField()
    index = IntegerField()
    time_collected = DateTimeField()
    batch_id = ForeignKeyField(Batch, backref='multiContainerImages')

class BBox(BaseModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4())
    x1 = IntegerField()
    y1 = IntegerField()
    x2 = IntegerField()
    y2 = IntegerField()
    tracker_id = IntegerField()
    image_id = ForeignKeyField(MultiContainerImage, backref='bboxes')

class SingleContainerImage(BaseModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4())
    height = IntegerField()
    width = IntegerField()
    time_collected = DateTimeField()
    predicted_category = TextField()
    tracker_id = IntegerField()
    batch_id = ForeignKeyField(Batch, backref='singleContainerImages')

all_tables = [
    Batch,
    MultiContainerImage,
    BBox,
    SingleContainerImage
]

def init_db():
    current_tables = db.get_tables()
    tables_to_create = list(filter(lambda e: str(e) not in current_tables, all_tables))
    db.create_tables(tables_to_create)
    db.execute_sql('PRAGMA foreign_keys = ON;')

def compute_accuracy(actual: int, expected: int):
    return 100.0 - (abs(expected - actual) / expected * 100.0)
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


def get_today_summary():
    now = datetime.datetime.now()
    start = datetime.datetime(now.year, now.month, now.day)
    res = list(Database.execute_sql(db,
        f'''select 
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
            from Batch
            where time_submitted is not null and unixepoch(time_started) > {int(start.timestamp())} and unixepoch(time_started) < {int(now.timestamp())}'''))[0]

    return TodaySummary(
        num_of_batches=res[0] if res[0] is not None else 0,
        count=res[1] if res[1] is not None else 0,
        can_count=res[2] if res[2] is not None else 0,
        plastic_count=res[3] if res[3] is not None else 0,
        drinkbox_count=res[4] if res[4] is not None else 0,
        gabletop_count=res[5] if res[5] is not None else 0,
        pouch_count=res[6] if res[6] is not None else 0,
        num_of_batches_with_expected=res[7] if res[7] is not None else 0,
        count_accuracy=res[8],
        can_accuracy=res[9],
        plastic_accuracy=res[10],
        drinkbox_accuracy=res[11],
        gabletop_accuracy=res[12],
        pouch_accuracy=res[13]
    )

def save_state(data_to_save: DataToSave):
    batch_dirs_created = set()

    shms: list[shared_memory.SharedMemory]= []

    try:
        for image in data_to_save.multi_container_images:
            if str(image.batch_id) not in batch_dirs_created:
                os.makedirs(f'images/{image.batch_id}/multi_container_images', exist_ok=True)
                os.makedirs(f'images/{image.batch_id}/single_container_images', exist_ok=True)
                batch_dirs_created.add(str(image.batch_id))
            shm = shared_memory.SharedMemory(name=str(image.id), track=False)
            shms.append(shm)
            decoded_frame = np.ndarray(image.frame_shape, np.uint8, buffer=shm.buf)
            cv2.imwrite(f'images/{image.batch_id}/multi_container_images/{image.id}.{image.index}.jpg', decoded_frame)

        for image in data_to_save.single_container_images:
            if str(image.batch_id) not in batch_dirs_created:
                os.makedirs(f'images/{image.batch_id}/multi_container_images', exist_ok=True)
                os.makedirs(f'images/{image.batch_id}/single_container_images', exist_ok=True)
                batch_dirs_created.add(str(image.batch_id))
            shm = shared_memory.SharedMemory(name=str(image.id), track=False)
            shms.append(shm)
            decoded_frame = np.ndarray(image.frame_shape, np.uint8, buffer=shm.buf)
            cv2.imwrite(f'images/{image.batch_id}/single_container_images/{image.id}.{image.detected_class}.jpg', decoded_frame)

        with db.atomic():
            if data_to_save.batch is not None:
                batch = Batch(
                    id=data_to_save.batch.id,
                    time_started=data_to_save.batch.time_started,
                    time_submitted=data_to_save.batch.time_submitted,
                    count=data_to_save.batch.count,
                    can_count=data_to_save.batch.can_count,
                    plastic_count=data_to_save.batch.plastic_count,
                    drinkbox_count=data_to_save.batch.drinkbox_count,
                    gabletop_count=data_to_save.batch.gabletop_count,
                    pouch_count=data_to_save.batch.pouch_count,
                    expected_count=data_to_save.batch.expected_count,
                    expected_can_count=data_to_save.batch.expected_can_count,
                    expected_plastic_count=data_to_save.batch.expected_plastic_count,
                    expected_drinkbox_count=data_to_save.batch.expected_drinkbox_count,
                    expected_gabletop_count=data_to_save.batch.expected_gabletop_count,
                    expected_pouch_count=data_to_save.batch.expected_pouch_count,
                    yolo_model=data_to_save.batch.yolo_model,
                    category_model=data_to_save.batch.category_model
                )
                updated = Batch.save(batch)
                if not updated:
                    Batch.save(batch, force_insert=True)

            multi_container_images = list(map(lambda e: MultiContainerImage(
                id=e.id,
                index=e.index,
                time_collected=e.time,
                height=e.frame_shape[0],
                width=e.frame_shape[1],
                batch_id=e.batch_id,
            ), data_to_save.multi_container_images))

            bboxes: list[BBox] = []
            for multi_container_image in data_to_save.multi_container_images:
                current_image_bboxes = list(map(lambda e: BBox(
                    id=uuid.uuid4(),
                    x1=e[0][0],
                    y1=e[0][1],
                    x2=e[0][2],
                    y2=e[0][3],
                    tracker_id=e[1],
                    image_id=multi_container_image.id
                ), zip(multi_container_image.detections.xyxy, multi_container_image.detections.tracker_id)))
                bboxes.extend(current_image_bboxes)

            single_container_images = list(map(lambda e: SingleContainerImage(
                id=e.id,
                time_collected=e.time,
                predicted_category=e.detected_class,
                height=e.frame_shape[0],
                width=e.frame_shape[1],
                tracker_id=e.tracker_id,
                batch_id=e.batch_id
            ), data_to_save.single_container_images))

            MultiContainerImage.bulk_create(batch_size=50, model_list=multi_container_images)
            BBox.bulk_create(batch_size=50, model_list=bboxes)
            SingleContainerImage.bulk_create(batch_size=50, model_list=single_container_images)
    finally:
        for shm in shms:
            shm.close()
