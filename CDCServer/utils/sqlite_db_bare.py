from peewee import *
from datetime import datetime, timedelta
import uuid

db = SqliteDatabase('resources/state.db')

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
    index_value = IntegerField(db_column="index")
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

def get_all_batches_from_day(day: datetime):

    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)

    batches = Batch.select().where((Batch.time_started > start) & (Batch.time_started < end))
    
    return list(batches)

def init_db():
    current_tables = db.get_tables()
    tables_to_create = list(filter(lambda e: str(e) not in current_tables, all_tables))
    db.create_tables(tables_to_create)
    db.execute_sql('PRAGMA foreign_keys = ON;')