from prisma import Client
import asyncio
import json


async def check_unknown_images():
    """Check how many images have UNKNOWN status in the database."""
    db = Client()
    await db.connect()

    try:
        # Count images with UNKNOWN status
        images = await db.image.find_many()

        image_id_to_chunk_id = {}

        for image in images:
            image_id_to_chunk_id[image.id] = image.chunkId

        with open('image_id_to_chunks.json', 'w') as f:
            json.dump(image_id_to_chunk_id, f, indent=4)


    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(check_unknown_images())
