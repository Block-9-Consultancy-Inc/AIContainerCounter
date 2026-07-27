from prisma import Client
import asyncio
import json
import uuid
from datetime import datetime, timezone


def open_json(filename):
    """Opens and reads a JSON file.

    Args:
        filename (str): The path to the JSON file.

    Returns:
        dict: The JSON data as a dictionary.
    """
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON in file '{filename}'.")
        return None


async def process_json_data():
    db = Client()
    await db.connect()

    file_path = '/workspace/CDCServer/roboflow_jobs.json'
    json_data = open_json(file_path)
    with_name_count = 0
    without_name_count = 0
    completed_jobs_count = 0
    incomplete_jobs_count = 0
    

    if json_data:
        ids = set()

        for roboflow_job in json_data:
            temp = roboflow_job['job_name'].split(' ')
            if roboflow_job['job_status'] == "Dataset":
                continue
            if len(temp) > 3 and not roboflow_job['job_name'].startswith('Added from Search'):
                with_name_count += 1
                roboflow_id = roboflow_job['job_name'].split(' ')[3]
                ids.add(roboflow_id)
                
                # Add verification session here, if it already doesn't exist


                
                
                # Check if job is complete (all images have corrections)
                job_complete = False

                for image in roboflow_job['images']:
                    # find image in database with image['file_name']
                    id: str = image['file_name'].split('.')[0]

                    # Get corrections for this image
                    corrections = await db.correction.find_many(where={'imageId': id})

                    if corrections:
                        job_complete = True
                        break

                if job_complete:
                    for image in roboflow_job['images']:
                        id: str = image['file_name'].split('.')[0]
                        db_image = await db.image.find_unique(where={'id': id})
                        if db_image:
                            # Update imageStatus to VERIFIED
                            await db.image.update(
                                where={'id': id},
                                data={'imageStatus': 'VERIFIED'}
                            )


                    # Create new verification session
                    current_time = datetime.now(timezone.utc)
                    verification_session = await db.verificationsession.create(
                        data={
                            'id': str(uuid.uuid4()),
                            'userId': roboflow_id,
                            'timeAssigned': current_time,
                            'timeCompleted': current_time
                        }
                    )
                    print(f"Created verification session for job: {roboflow_job['job_name']}")

                    # For each image we want to make an entry in the ImageInVerificationSession table:
                    for image in roboflow_job['images']:
                        
                        id: str = image['file_name'].split('.')[0]
                        #find if verification session already exists in ImageInVerificationSession
                        # if it does continue
                        existing_entry = await db.imageinverificationsession.find_first(
                            where={
                                'verificationSessionId': verification_session.id,
                                'imageId': id
                            }
                        )
                        if existing_entry:
                            continue

                        db_image = await db.image.find_unique(where={'id': id})
                        if db_image:
                            # Create ImageInVerificationSession entry
                            await db.imageinverificationsession.create(
                                data={
                                    'verificationSessionId': verification_session.id,
                                    'imageId': id
                                }
                            )
                        # for corrections in each image add verificationSessionId
                        corrections = await db.correction.find_many(where={'imageId': id})
                        for correction in corrections:
                            await db.correction.update(
                                where={'id': correction.id},
                                data={'verificationSessionId': verification_session.id}
                            )
                    # print(f"COMPLETED JOB: {roboflow_job['job_name']}")
                    completed_jobs_count += 1
                else:
                    for image in roboflow_job['images']:
                        id: str = image['file_name'].split('.')[0]
                        db_image = await db.image.find_unique(where={'id': id})
                        if db_image:
                            # Update imageStatus to ON_QUEUE
                            await db.image.update(
                                where={'id': id},
                                data={'imageStatus': 'ON_QUEUE'}
                            )
                        
                    print(f"INCOMPLETE JOB: {roboflow_job['job_name']}")
                    incomplete_jobs_count += 1
                    for image in roboflow_job['images']:
                        id: str = image['file_name'].split('.')[0]
                        db_image = await db.image.find_unique(where={'id': id})
                        if db_image:
                           if (db_image.imageStatus == 'UNKNOWN'):
                                print("Oh oh")

            else:
                without_name_count += 1
                if roboflow_job['job_name'].startswith('Avoid') or roboflow_job['job_name'].startswith('Empty'):
                    continue
                for image in roboflow_job['images']:
                    id: str = image['file_name'].split('.')[0]
                    db_image = await db.image.find_unique(where={'id': id})
                    if db_image:
                        # Update imageStatus to ON_QUEUE
                        await db.image.update(
                            where={'id': id},
                            data={'imageStatus': 'ON_QUEUE'}
                        )
                print(f"Job without name: {roboflow_job['job_name']}")


            # Finally check if the any image has unknown status
            
        print(f"Total jobs with name: {with_name_count}")
        print(f"Total jobs without name: {without_name_count}")
        print(f"Completed jobs: {completed_jobs_count}")
        print(f"Incomplete jobs: {incomplete_jobs_count}")
        print(f"Total unique Roboflow IDs: {len(ids)}")
        print(f"Unique Roboflow IDs: {ids}")
    else:
        print("Failed to load JSON data.")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(process_json_data())
