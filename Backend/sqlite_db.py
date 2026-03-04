from peewee import *
import datetime
from counter import Counter
import uuid

db = SqliteDatabase('state.db')

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


class MultiContainerImage(BaseModel):
    id = UUIDField(primary_key=True)
    height = IntegerField()
    width = IntegerField()
    time_collected = DateTimeField()
    batch_id = ForeignKeyField(Batch, backref='multiContainerImages')

class SingleContainerImage(BaseModel):
    id = UUIDField(primary_key=True)
    height = IntegerField()
    width = IntegerField()
    time_collected = DateTimeField()
    batch_id = ForeignKeyField(Batch, backref='singleContainerImages')

all_tables = [
    Batch,
    MultiContainerImage,
    SingleContainerImage
]

def init_db():
    current_tables = db.get_tables()
    tables_to_create = list(filter(lambda e: str(e) not in current_tables, all_tables))
    db.create_tables(tables_to_create)

def save_batch(counter: Counter):
    Batch.create(
        id=str(uuid.uuid4()),
        time_started=counter.time_batch_started,
        count=counter.line_zone.in_count,
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
    )