from prisma import Client
import asyncio


async def check_unknown_images():
    """Check how many images have UNKNOWN status in the database."""
    db = Client()
    await db.connect()

    try:
        # Count images with UNKNOWN status
        unknown_count = await db.image.count(where={'imageStatus': 'UNKNOWN'})
        print(f"Total images with UNKNOWN status: {unknown_count}")

        # Get all possible image statuses for comparison
        all_statuses = await db.image.group_by(
            by=['imageStatus'],
            count=True
        )

        print("\nImage status distribution:")
        for status_group in all_statuses:
            print(f"  {status_group['imageStatus']}: {status_group['_count']}")

        # Get min and max timeTaken for UNKNOWN status images
        if unknown_count > 0:
            # Get all UNKNOWN images to find min/max times
            unknown_images_time = await db.image.find_many(
                where={'imageStatus': 'UNKNOWN'}
            )
            
            if unknown_images_time:
                times = [img.timeTaken for img in unknown_images_time]
                min_time = min(times)
                max_time = max(times)
                print(f"\nTime range for UNKNOWN status images:")
                print(f"  Earliest: {min_time}")
                print(f"  Latest: {max_time}")
            
        else:
            print("\nNo images with UNKNOWN status found.")



    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(check_unknown_images())
