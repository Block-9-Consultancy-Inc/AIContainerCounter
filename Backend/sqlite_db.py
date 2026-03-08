from peewee import *
import datetime
import uuid
import os
import cv2
from dataclasses import dataclass
from supervision import Detections
import numpy as np

db = SqliteDatabase('resources/state.db')

@dataclass
class MultiContainerImageToSave:
    index: int
    time: datetime
    detections: Detections
    frame: np.ndarray
    id: uuid.UUID
    batch_id: uuid.UUID

@dataclass
class SingleContainerImageToSave:
    id: uuid.UUID
    time: datetime
    detected_class: str
    frame: np.ndarray
    tracker_id: int
    batch_id: uuid.UUID

@dataclass
class BatchToSave:
    id: uuid.UUID
    time_started: datetime
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
    time_submitted = DateTimeField(default=datetime.datetime.now)
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

def save_state(data_to_save: DataToSave):
    batch_dirs_created = set()

    for image in data_to_save.multi_container_images:
        if str(image.batch_id) not in batch_dirs_created:
            os.makedirs(f'images/{image.batch_id}/multi_container_images', exist_ok=True)
            os.makedirs(f'images/{image.batch_id}/single_container_images', exist_ok=True)
            batch_dirs_created.add(str(image.batch_id)) 
        cv2.imwrite(f'images/{image.batch_id}/multi_container_images/{image.id}.{image.index}.jpg', image.frame)

    for image in data_to_save.single_container_images:
        if str(image.batch_id) not in batch_dirs_created:
            os.makedirs(f'images/{image.batch_id}/multi_container_images', exist_ok=True)
            os.makedirs(f'images/{image.batch_id}/single_container_images', exist_ok=True)
            batch_dirs_created.add(str(image.batch_id))
        cv2.imwrite(f'images/{image.batch_id}/single_container_images/{image.id}.{image.detected_class}.jpg', image.frame)

    with db.atomic():
        if data_to_save.batch is not None:
            batch = Batch(
                id=data_to_save.batch.id,
                time_started=data_to_save.batch.time_started,
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
            height=e.frame.shape[0],
            width=e.frame.shape[1],
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
            height=e.frame.shape[0],
            width=e.frame.shape[1],
            batch_id=e.batch_id
        ), data_to_save.single_container_images))

        MultiContainerImage.bulk_create(batch_size=50, model_list=multi_container_images)
        BBox.bulk_create(batch_size=50, model_list=bboxes)
        SingleContainerImage.bulk_create(batch_size=50, model_list=single_container_images)


'''
select avg(1.0 - (abs((count * 1.0) - (expected_count* 1.0))/(expected_count * 1.0))) as overallaccuracy, avg(1.0 - (abs((can_count * 1.0) - (expected_can_count* 1.0))/(expected_can_count * 1.0))) as canaccuracy, avg(1.0 - (abs((plastic_count * 1.0) - (expected_plastic_count* 1.0))/(expected_plastic_count * 1.0))) as plasticaccuracy, avg(1.0 - (abs((drinkbox_count * 1.0) - (expected_drinkbox_count* 1.0))/(expected_drinkbox_count * 1.0))) as drinkboxaccuracy, avg(1.0 - (abs((gabletop_count * 1.0) - (expected_gabletop_count* 1.0))/(expected_gabletop_count * 1.0))) as gabletopaccuracy, avg(1.0 - (abs((pouch_count * 1.0) - (expected_pouch_count* 1.0))/(expected_pouch_count * 1.0))) as pouchaccuracy, count(id) as num_of_batches from Batch where (julianday(datetime('now', 'localtime')) - julianday(time_submitted)) * 24 > 10;
'''