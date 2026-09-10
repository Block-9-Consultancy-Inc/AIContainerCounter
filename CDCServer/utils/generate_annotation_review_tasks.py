from prisma import Client
import asyncio
from time import perf_counter
from datetime import datetime, timezone
import os
from prisma.models import Image, VerificationSession
from server.routers.bbox_correction import apply_corrections, model_to_correction, generate_image_with_bounding_boxes
import random

async def get_random_images_for_user(db: Client, user_id: str, take = 50):
    results = await db.query_raw("""
            select distinct i.id, random() as order_value
            from "Image" i 
                left join "Batch" b on b.id = i."batchId" 
                left join "ImageInVerificationSession" ivs on i.id = ivs."imageId"
                left join "VerificationSession" vs on vs.id = ivs."verificationSessionId" 
            where vs."userId" = $1 and b."batchType" = 'DENSIFIER' and i."imageStatus" = 'VERIFIED'
            order by order_value
            limit $2;
        """, user_id, take)

    return list(map(lambda e: e.get('id'), results))

async def get_labels_for_tasks(task_ids: list[str]):
    db = Client(
        http={
            'timeout': 300
        }
    )
    await db.connect()

    try:
        verification_sessions = await db.verificationsession.find_many(
                where={ 'id': { 'in': task_ids } }
            )

        verification_sessions_map = {e.id: e for e in verification_sessions}

        image_in_verification_sessions = await db.imageinverificationsession.find_many(
            where={ 'verificationSessionId': { 'in': list(map(lambda e: e.id, verification_sessions)) }},
            include={
                        'corrections': True,
                        'image': {
                            'include': {
                                'bboxes': True
                            }
                        }
                    },
            order={ 'verificationSessionId': 'asc' }
        )
        print('got back from db')

        image_in_verification_sessions_map = {e.id: [] for e in verification_sessions}

        for image_in_verification_session in image_in_verification_sessions:
            image_in_verification_sessions_map.get(image_in_verification_session.verificationSessionId).append(image_in_verification_session)
        
        for task_id in task_ids:
            verification_session = verification_sessions_map.get(task_id)
            os.makedirs(f'resources/tasks/{verification_session.userId}/{task_id}', exist_ok=True)
            images: list[Image] = []
            for image_in_verification_session in image_in_verification_sessions_map.get(task_id):
                image = image_in_verification_session.image
                image_in_verification_session.verificationSession = verification_sessions_map.get(image_in_verification_session.verificationSessionId)
                image.imageInVerificationSession = [image_in_verification_session]
                images.append(image)
            for image in images:
                before_bboxes = list(map(lambda e: { 'uuid': e.id, 'x': e.x1, 'y': e.y1, 'w': e.x2 - e.x1, 'h': e.y2 - e.y1, 'label': e.label }, image.bboxes))
                corrections = list(map(lambda e: model_to_correction(e), image.imageInVerificationSession[0].corrections))
                print(f'{image.id}: num of corrections: {len(corrections)}')
                after = apply_corrections(before_bboxes, corrections)
                generate_image_with_bounding_boxes(after, f"resources/densifier_images/{image.id}.jpg", f'resources/tasks/{verification_session.userId}/{task_id}/{image.id}.jpg')
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        await db.disconnect()

async def generate_annotation_review_tasks():
    db = Client(
        http={
            'timeout': 300
        }
    )
    await db.connect()

    users = [
        "TH250627",
        "YH250627",
        "FF250629",
        "FK250627",
        "DA250321",
        "JT240625",
        "FS250706",
        "NS250705",
        "PS250705",
        "BA241212",
        "TI250709",
        "RS250705",
        "FN250607",
        "AR250705",
        "NS241213",
    ]

    try:
        print('getting data from db')
        start_time = perf_counter()
        verification_sessions = await db.verificationsession.find_many(
            where={ 'AND': [
                    {'timeCompleted': { 'not': { 'equals': None } }},
                    { 'timeAssigned': { 'gt': datetime(2025, 8, 14, 10, 40, tzinfo=timezone.utc)}}
                ]},
            order={ 'userId': 'desc' },
            include={
                'imageInVerificationSession': {
                    'include': {
                        'corrections': True,
                        'image': {
                            'include': {
                                'bboxes': True
                            }
                        }
                    }
                }
            }
        )
        end_time = perf_counter()
        print(f'got back from db in {end_time - start_time} seconds')
        print(f'got {len(verification_sessions)} verification sessions')

        verification_sessions_per_user: dict[str, list[VerificationSession]] = { user_id: [] for user_id in users }

        for verification_session in verification_sessions:
            verification_sessions_per_user[verification_session.userId].append(verification_session)


        # verification_sessions = await db.verificationsession.find_many(
        #     where={ 'id': '7250a4f3-37a7-4cb7-ae7b-77eaf88bf9f3' },
        #     take=10
        # )

        # verification_sessions_map = {e.id: e for e in verification_sessions}

        # image_in_verification_sessions = await db.imageinverificationsession.find_many(
        #     where={ 'verificationSessionId': { 'in': list(map(lambda e: e.id, verification_sessions)) }},
        #     include={
        #                 'corrections': True,
        #                 'image': {
        #                     'include': {
        #                         'bboxes': True
        #                     }
        #                 }
        #             }
        # )
        # print('got back from db')
        # images: List[Image] = []
        # for image_in_verification_session in image_in_verification_sessions:
        #     image = image_in_verification_session.image
        #     image_in_verification_session.verificationSession = verification_sessions_map.get(image_in_verification_session.verificationSessionId)
        #     image.imageInVerificationSession = [image_in_verification_session]
        #     images.append(image)

        # images = await db.image.find_many(
        #     where={ 'AND':  [
        #         { 'imageStatus': ImageStatus.VERIFIED },
        #         { 'batch': { 'is': {
        #             'batchType': BatchType.DENSIFIER
        #         }}}
        #     ]},
        #     include={
        #         'bboxes': True,
        #         'imageInVerificationSession': { 
        #             'include': {
        #                 'corrections': True
        #             }
        #         }
        #     },
        #     take=500
        # )
        for user_id in users:
            verification_sessions_for_user = verification_sessions_per_user.get(user_id)
            for verification_session in verification_sessions_for_user:
                os.makedirs(f'resources/annotators_review/{user_id}/{verification_session.id}', exist_ok=True)
                images: list[Image] = []
                for image_in_verification_session in verification_session.imageInVerificationSession:
                    image = image_in_verification_session.image
                    image_in_verification_session.verificationSession = verification_session
                    image.imageInVerificationSession = [image_in_verification_session]
                    images.append(image)

                random.shuffle(images)

                existing_images = list(map(lambda e: e.replace('.jpg', ''), os.listdir(f'resources/annotators_review/{user_id}/{verification_session.id}')))

                images = list(filter(lambda e: e.id in existing_images, images))

                for image in images[:2]:
                    before_bboxes = list(map(lambda e: { 'uuid': e.id, 'x': e.x1, 'y': e.y1, 'w': e.x2 - e.x1, 'h': e.y2 - e.y1, 'label': e.label }, image.bboxes))
                    corrections = list(map(lambda e: model_to_correction(e), image.imageInVerificationSession[0].corrections))
                    print(f'{image.id}: num of corrections: {len(corrections)}')
                    after = apply_corrections(before_bboxes, corrections)
                    generate_image_with_bounding_boxes(after, f"resources/densifier_images/{image.id}.jpg", f'resources/annotators_review/{user_id}/{verification_session.id}/{image.id}.jpg')
    except Exception as e:
            print(f"Error occurred: {e}")
    finally:
        await db.disconnect()


if __name__ == '__main__':
    asyncio.run(generate_annotation_review_tasks())