from peewee import *
import datetime
from counter import Counter
import uuid
import os
import cv2

db = SqliteDatabase('resources/state.db')

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

def save_batch(counter: Counter):
    os.makedirs(f'images/{counter.current_batch_uuid}/multi_container_images', exist_ok=True)
    os.makedirs(f'images/{counter.current_batch_uuid}/single_container_images', exist_ok=True)

    for index, (_, _, frame, id) in enumerate(counter.batch_multi_container_images):
        cv2.imwrite(f'images/{counter.current_batch_uuid}/multi_container_images/{id}.{index}.jpg', frame)

    for _, predicted_class, frame, id in counter.batch_single_container_images:
        cv2.imwrite(f'images/{counter.current_batch_uuid}/single_container_images/{id}.{predicted_class}.jpg', frame)

    with db.atomic():
        Batch.create(
            id=counter.current_batch_uuid,
            time_started=counter.time_batch_started,
            count=counter.center_line_zone.in_count,
            can_count=counter.category_counts.get('can'),
            plastic_count=counter.category_counts.get('plastic'),
            drinkbox_count=counter.category_counts.get('drinkbox'),
            gabletop_count=counter.category_counts.get('gabletop'),
            pouch_count=counter.category_counts.get('pouch'),
            expected_count=sum(list(map(lambda e: e[1], counter.expected_category_counts.items()))) if counter.expected_category_counts is not None else None,
            expected_can_count=counter.expected_category_counts.get('can') if counter.expected_category_counts is not None else None,
            expected_plastic_count=counter.expected_category_counts.get('plastic') if counter.expected_category_counts is not None else None,
            expected_drinkbox_count=counter.expected_category_counts.get('drinkbox') if counter.expected_category_counts is not None else None,
            expected_gabletop_count=counter.expected_category_counts.get('gabletop') if counter.expected_category_counts is not None else None,
            expected_pouch_count=counter.expected_category_counts.get('pouch') if counter.expected_category_counts is not None else None,
            yolo_model=counter.yolo_model,
            category_model=counter.category_model
        )
        multi_container_images = list(map(lambda e: MultiContainerImage(
            id=e[1][3],
            index=e[0],
            time_collected=e[1][0],
            height=e[1][2].shape[0],
            width=e[1][2].shape[1],
            batch_id=counter.current_batch_uuid
        ), enumerate(counter.batch_multi_container_images)))

        bboxes: list[BBox] = []
        for _, xyxys, _, image_id in counter.batch_multi_container_images:
            current_image_bboxes = list(map(lambda e: BBox(
                id=uuid.uuid4(),
                x1=e[0],
                y1=e[1],
                x2=e[2],
                y2=e[3],
                image_id=image_id
            ), xyxys))
            bboxes.extend(current_image_bboxes)

        single_container_images = list(map(lambda e: SingleContainerImage(
            id=e[3],
            time_collected=e[0],
            predicted_category=e[1],
            height=e[2].shape[0],
            width=e[2].shape[1],
            batch_id=counter.current_batch_uuid
        ), counter.batch_single_container_images))

        MultiContainerImage.bulk_create(batch_size=50, model_list=multi_container_images)
        BBox.bulk_create(batch_size=50, model_list=bboxes)
        SingleContainerImage.bulk_create(batch_size=50, model_list=single_container_images)


'''
select avg(1.0 - (abs((count * 1.0) - (expected_count* 1.0))/(expected_count * 1.0))) as overallaccuracy, avg(1.0 - (abs((can_count * 1.0) - (expected_can_count* 1.0))/(expected_can_count * 1.0))) as canaccuracy, avg(1.0 - (abs((plastic_count * 1.0) - (expected_plastic_count* 1.0))/(expected_plastic_count * 1.0))) as plasticaccuracy, avg(1.0 - (abs((drinkbox_count * 1.0) - (expected_drinkbox_count* 1.0))/(expected_drinkbox_count * 1.0))) as drinkboxaccuracy, avg(1.0 - (abs((gabletop_count * 1.0) - (expected_gabletop_count* 1.0))/(expected_gabletop_count * 1.0))) as gabletopaccuracy, avg(1.0 - (abs((pouch_count * 1.0) - (expected_pouch_count* 1.0))/(expected_pouch_count * 1.0))) as pouchaccuracy, count(id) as num_of_batches from Batch where (julianday(datetime('now', 'localtime')) - julianday(time_submitted)) * 24 > 10;
'''