import uuid
from sqlmodel import Field, SQLModel, create_engine, Session, select, update, text, Relationship
from sqlalchemy.orm import contains_eager
import datetime

DATABASE_PATH = '/home/counti/Projects/AIContainerCounter/Backend/resources/state.db'
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

def get_all_batches_from_day(day: datetime.datetime):
    start = datetime.datetime(day.year, day.month, day.day)
    end = start + datetime.timedelta(days=1)

    with Session(engine) as session:
        statement = (select(Batch)
            # .join(Batch.multi_container_images)
            # .join(MultiContainerImage.bboxes)
            # .options(contains_eager(Batch.multi_container_images).contains_eager(MultiContainerImage.bboxes))
            .where(
            (Batch.time_submitted > start) & 
            (Batch.time_submitted < end)
        ).order_by(Batch.time_submitted.desc()))
        batches = session.exec(statement).all()
        return list(batches)

def get_batch_multi_container_images(batch_id: str):
    with Session(engine) as session:
        statement = (select(MultiContainerImage)
            # .join(Batch.multi_container_images)
            .outerjoin(MultiContainerImage.bboxes)
            .options(contains_eager(MultiContainerImage.bboxes))
            .where(MultiContainerImage.batch_id == batch_id).order_by(MultiContainerImage.index.asc()))
        images = session.exec(statement).unique().all()
        return list(images)
    
def get_batch_single_container_images(batch: Batch):
    with Session(engine) as session:
        statement = (select(SingleContainerImage)
            # .join(Batch.multi_container_images)
            .where(SingleContainerImage.batch_id == batch.id))
        images = session.exec(statement).all()
        return list(images)

if __name__ == '__main__':

    images = get_batch_multi_container_images('3a52cd79-b6f6-4d77-87a2-9147a737d0fa')
    indexes = list(map(lambda e: e.index, images))
    print(f'num images: {len(indexes)}')
    # print(indexes)
    missing_indexes = []
    current_index = 0
    for index in indexes:
        print(f'{index=}, {current_index=}')
        if index == current_index:
            current_index += 1
            continue
        while index != current_index:
            missing_indexes.append(current_index)
            current_index += 1
            print(f'{index=}, {current_index=}, MISSING: {current_index - 1}')
        current_index += 1
    # print(f'missing indexes: {len(missing_indexes)}')
    print(missing_indexes)