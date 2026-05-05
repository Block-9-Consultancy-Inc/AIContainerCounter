import asyncio
import random
import uuid
from datetime import datetime, timedelta
from faker import Faker
from prisma import Prisma
from prisma.enums import CountiUnitStatus, DatasetSplit, BBoxType
from prisma.models import Image # Import Image to fetch dimensions later
import os
from dotenv import load_dotenv
import traceback

# Load environment variables (for DB_URL)
load_dotenv()

# --- Configuration ---
NUM_ROWS_TARGET = 50 # Target number of rows for most tables
fake = Faker()

# --- Helper Functions ---

def random_enum(enum_class):
    """Selects a random member from a Prisma enum."""
    return random.choice(list(enum_class))

async def clear_database(db: Prisma):
    """Deletes data in reverse order of dependency."""
    print("Clearing existing data...")
    # Order matters to avoid foreign key constraint errors
    await db.bbox.delete_many()
    print("- BBoxes deleted.")
    await db.imageindatasetsnapshot.delete_many()
    print("- ImageInDatasetSnapshots deleted.")
    # Need to break the self-relation before deleting Models
    await db.trainedmodel.update_many(data={'checkpointId': None}, where={})
    print("- Model checkpoints cleared.")
    await db.trainedmodel.delete_many()
    print("- Models deleted.")
    await db.datasetsnapshot.delete_many()
    print("- DatasetSnapshots deleted.")
    await db.image.delete_many()
    print("- Images deleted.")
    await db.countiunit.delete_many()
    print("- CountiUnits deleted.")
    print("Database cleared.")


async def populate_counti_units(db: Prisma) -> list[str]:
    """Populates the CountiUnit table."""
    print(f"Populating {NUM_ROWS_TARGET} CountiUnits...")
    units_data = []
    for _ in range(NUM_ROWS_TARGET):
        units_data.append({
            'id': str(uuid.uuid4()), # Explicitly provide ID if not default UUID in schema
            'location': fake.address(),
            'status': random_enum(CountiUnitStatus),
            # 'registered' and 'updated' handled by Prisma defaults/triggers
        })
    await db.countiunit.create_many(data=units_data, skip_duplicates=True)
    print("CountiUnits populated.")
    # Fetch the actual IDs created (or use the generated ones if no conflicts)
    created_units = await db.countiunit.find_many()
    return [unit.id for unit in created_units]

async def populate_dataset_snapshots(db: Prisma) -> list[str]:
    """Populates the DatasetSnapshot table."""
    print(f"Populating {NUM_ROWS_TARGET} DatasetSnapshots...")
    snapshots_data = []
    for _ in range(NUM_ROWS_TARGET):
        snapshots_data.append({
            # 'id' handled by Prisma default
            'description': fake.sentence(),
            # 'created' handled by Prisma default
        })
    # create_many doesn't easily return IDs with default UUIDs
    # Create one by one or create_many then fetch
    created_ids = []
    # Let's create one by one to easily get IDs back
    for data in snapshots_data:
         snapshot = await db.datasetsnapshot.create(data=data)
         created_ids.append(snapshot.id)
    # Alternative: Use create_many then fetch all
    # await db.datasetsnapshot.create_many(data=snapshots_data, skip_duplicates=True)
    # created_snapshots = await db.datasetsnapshot.find_many(select={'id': True})
    # created_ids = [snap.id for snap in created_snapshots]

    print("DatasetSnapshots populated.")
    return created_ids

async def populate_images(db: Prisma, counti_unit_ids: list[str]) -> list[str]:
    """Populates the Image table."""
    if not counti_unit_ids:
        print("Warning: No CountiUnit IDs provided for Image population.")
        return []
    print(f"Populating {NUM_ROWS_TARGET} Images...")
    images_data = []
    for _ in range(NUM_ROWS_TARGET):
        images_data.append({
            # 'id' handled by Prisma default
            'fileExtension': random.choice(['jpg', 'png', 'jpeg']),
            'height': random.randint(200, 2000),
            'width': random.randint(200, 2000),
            'timeTaken': fake.date_time_this_decade(), # Set explicitly, @updatedAt might behave differently
            'countiUnit': random.choice(counti_unit_ids), # Schema shows String, link to ID
            'chunkId': str(uuid.uuid4()),
        })

    created_ids = []
    # Create one by one to get IDs back easily
    for data in images_data:
        image = await db.image.create(data=data)
        created_ids.append(image.id)

    # Alternative: create_many then fetch
    # await db.image.create_many(data=images_data, skip_duplicates=True)
    # created_images = await db.image.find_many(select={'id': True})
    # created_ids = [img.id for img in created_images]

    print("Images populated.")
    return created_ids

async def populate_trained_models(db: Prisma, dataset_snapshot_ids: list[str]) -> list[str]:
    """Populates the Model table, initially without checkpoints."""
    if not dataset_snapshot_ids:
        print("Warning: No DatasetSnapshot IDs provided for Trained Model population.")
        return []
    print(f"Populating {NUM_ROWS_TARGET} Trained Models...")
    models_data = []
    for _ in range(NUM_ROWS_TARGET):
         models_data.append({
            # 'id' handled by Prisma default
            'description': fake.sentence() if random.random() > 0.2 else None,
            'datasetSnapshotId': random.choice(dataset_snapshot_ids),
            # 'trained' handled by Prisma default
            # 'checkpointId' will be set later
        })

    created_ids = []
    for data in models_data:
        model = await db.trainedmodel.create(data=data)
        created_ids.append(model.id)

    # Alternative: create_many then fetch
    # await db.trainedmodel.create_many(data=models_data, skip_duplicates=True)
    # created_models = await db.trainedmodel.find_many(select={'id': True})
    # created_ids = [m.id for m in created_models]

    print("Trained Models populated.")
    return created_ids

async def update_model_checkpoints(db: Prisma, model_ids: list[str]):
    """Updates some models to add checkpoint relationships."""
    if len(model_ids) < 2:
        print("Not enough models to create checkpoint relationships.")
        return
    print("Adding checkpoint relationships to Models...")
    updates = 0
    for model_id in model_ids:
        # ~30% chance to add a checkpoint
        if random.random() < 0.3:
            # Pick a *different* model ID as the checkpoint
            possible_checkpoints = [id for id in model_ids if id != model_id]
            if possible_checkpoints:
                checkpoint_id = random.choice(possible_checkpoints)
                await db.trainedmodel.update(
                    where={'id': model_id},
                    data={'checkpointId': checkpoint_id}
                )
                updates += 1
    print(f"Added {updates} checkpoint relationships.")


async def populate_image_in_dataset_snapshots(db: Prisma, dataset_snapshot_ids: list[str], image_ids: list[str]):
    """Populates the linking table ImageInDatasetSnapshot."""
    if not dataset_snapshot_ids or not image_ids:
        print("Warning: Need both DatasetSnapshot and Image IDs for ImageInDatasetSnapshot population.")
        return
    print(f"Populating {NUM_ROWS_TARGET} ImageInDatasetSnapshot links...")

    links_data = []
    created_pairs = set() # Keep track of pairs to ensure uniqueness for composite key

    attempts = 0
    max_attempts = NUM_ROWS_TARGET * 5 # Limit attempts to avoid infinite loop if few unique pairs possible

    while len(links_data) < NUM_ROWS_TARGET and attempts < max_attempts:
        snapshot_id = random.choice(dataset_snapshot_ids)
        img_id = random.choice(image_ids)
        pair = (snapshot_id, img_id)

        if pair not in created_pairs:
            links_data.append({
                'datasetSnapshotId': snapshot_id,
                'imageId': img_id,
                'split': random_enum(DatasetSplit)
            })
            created_pairs.add(pair)
        attempts += 1

    if not links_data:
        print("Could not generate any unique ImageInDatasetSnapshot links.")
        return

    await db.imageindatasetsnapshot.create_many(data=links_data, skip_duplicates=True) # Skip if somehow duplicates generated despite check
    print(f"ImageInDatasetSnapshot links populated (attempted {NUM_ROWS_TARGET}, created {len(links_data)} unique).")


async def populate_bboxes(db: Prisma, image_ids: list[str], model_ids: list[str]):
    """Populates the BBox table."""
    if not image_ids:
        print("Warning: No Image IDs provided for BBox population.")
        return

    print(f"Populating at least {NUM_ROWS_TARGET} BBoxes...")
    bboxes_created_count = 0
    # Create BBoxes one by one as we need image dimensions
    while bboxes_created_count < NUM_ROWS_TARGET:
        image_id = random.choice(image_ids)
        # Fetch the specific image to get its dimensions
        image = await db.image.find_unique(where={'id': image_id}, include={'bboxes': False}) # Exclude bboxes to avoid large payload if already populated
        if not image:
            print(f"Warning: Image with ID {image_id} not found. Skipping BBox creation.")
            continue

        # Ensure coordinates are valid
        if image.width <= 1 or image.height <= 1:
             print(f"Warning: Image {image.id} has invalid dimensions ({image.width}x{image.height}). Skipping BBox.")
             continue

        x1 = random.randint(0, image.width - 1)
        y1 = random.randint(0, image.height - 1)
        x2 = random.randint(x1 + 1, image.width)
        y2 = random.randint(y1 + 1, image.height)

        bbox_type = random_enum(BBoxType)
        linked_model_id = None
        # Only link detections to models (optional)
        if bbox_type == BBoxType.DETECTION and model_ids and random.random() > 0.3: # 70% chance to link a detection
            linked_model_id = random.choice(model_ids)

        bbox_data = {
            # 'id' handled by Prisma default
            'imageId': image_id,
            'label': fake.word(),
            'bboxType': bbox_type,
            'x1': x1,
            'y1': y1,
            'x2': x2,
            'y2': y2,
            'trainedModelId': linked_model_id,
        }
        await db.bbox.create(data=bbox_data)
        bboxes_created_count += 1
        if bboxes_created_count % 25 == 0: # Print progress
             print(f"  ... {bboxes_created_count} BBoxes created ...")

    print(f"BBoxes populated ({bboxes_created_count} total).")


# --- Main Execution ---

async def main():
    """Main function to connect, populate, and disconnect."""
    db = Prisma(log_queries=False) # Set log_queries=True for debugging SQL
    try:
        print("Connecting to database...")
        await db.connect()
        print("Connected.")

        # Clear existing data (optional, be careful!)
        await clear_database(db)

        # Populate in order of dependency
        counti_unit_ids = await populate_counti_units(db)
        dataset_snapshot_ids = await populate_dataset_snapshots(db)
        image_ids = await populate_images(db, counti_unit_ids)
        model_ids = await populate_trained_models(db, dataset_snapshot_ids)
        await update_model_checkpoints(db, model_ids) # Add self-relations after initial creation
        await populate_image_in_dataset_snapshots(db, dataset_snapshot_ids, image_ids)
        await populate_bboxes(db, image_ids, model_ids) # Depends on Images and optionally Models

        print("\nDatabase population complete.")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        print(traceback.format_exc())

    finally:
        if db.is_connected():
            print("Disconnecting from database...")
            await db.disconnect()
            print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(main())