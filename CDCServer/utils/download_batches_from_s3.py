import logging
from pathlib import Path
import asyncio
import aioboto3
from botocore.exceptions import ClientError
import aiofiles
import datetime
import json
import tqdm
import os

from typing import Union

import aiofiles.os

async def path_exists(path: Union[Path, str]) -> bool:
    try:
        await aiofiles.os.stat(str(path))
    except Exception:
        # Non-encodable path
        return False
    return True

async def download_s3_object_async(s3_client, bucket_name, object_key, dest_path):
    try:
        file_exists = await path_exists(dest_path)
        if file_exists:
            return
        response = await s3_client.get_object(Bucket=bucket_name, Key=object_key)
        async with aiofiles.open(dest_path, "wb") as f:
            async for chunk in response["Body"].iter_chunks():
                await f.write(chunk)
        print(f"File '{object_key}' downloaded to '{dest_path}' successfully.")
    except Exception as e:
        print(f"Error downloading file: {e}")

async def log_failure(
    log_file_path: Path,
    lock: asyncio.Lock,
    local_path: Path | str,
    s3_key: str,
    error_msg: str,
):
    """Asynchronously logs a failed upload entry to the JSON Lines failure log."""
    async with lock:  # Ensure exclusive write access
        try:
            async with aiofiles.open(log_file_path, mode="a", encoding="utf-8") as f:
                failure_entry = {
                    "local_path": str(
                        local_path
                    ),  # Ensure Path object is converted to string
                    "s3_key": s3_key,
                    "error": error_msg,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                }
                await f.write(json.dumps(failure_entry) + "\n")
        except Exception as e:
            # Log error about logging itself, but don't stop the main process
            logging.error(f"!!! Failed to write to failure log {log_file_path}: {e}")

async def download_file_async(
    s3_client,
    local_path: Path,
    bucket: str,
    s3_key: str,
    failure_log_path: Path,
    failure_log_lock: asyncio.Lock,
) -> bool:
    """
    Asynchronously reads a file, uploads it to S3, and logs failures.
    Returns True on success, False on failure.
    """
    error_message = ""
        
    try:
        response = await s3_client.get_object(Bucket=bucket, Key=s3_key)
        async with aiofiles.open(local_path, "wb") as f:
            async for chunk in response["Body"].iter_chunks():
                await f.write(chunk)
        # Success, no need to log anything here for failures
        # logging.info(f"Successfully uploaded {local_path} to s3://{bucket}/{s3_key}") # Reduce log noise
        return True
    except ClientError as e:
        error_message = f"S3 ClientError: {e}"
        logging.error(
            f"Failed download s3://{bucket}/{s3_key} to {local_path}: {error_message}"
        )
        await log_failure(
            failure_log_path, failure_log_lock, local_path, s3_key, error_message
        )
        return False
    except Exception as e:
        error_message = f"Unexpected error: {e}"
        logging.error(
            f"Failed upload {local_path} to s3://{bucket}/{s3_key}: {error_message}"
        )
        await log_failure(
            failure_log_path, failure_log_lock, local_path, s3_key, error_message
        )
        return False

async def process_download_batches(
    files_to_download: list[tuple[Path, str]],
    bucket: str,
    aws_region: str | None,
    aws_profile: str | None,
    key: str,
    key_id: str,
    batch_size: int,
    failure_log_path: Path,
    desc: str = "Downloading Files",  # Description for tqdm
):
    """
    Processes a list of file downloads asynchronously in batches with progress bar and failure logging.
    """
    total_files_to_attempt = len(files_to_download)
    if not total_files_to_attempt:
        logging.info("No files provided for upload processing.")
        return 0, 0  # No successes, no failures

    logging.info(f"Starting asynchronous download of {total_files_to_attempt} files...")

    # Create a lock for writing to the failure log file
    failure_log_lock = asyncio.Lock()

    # Use aioboto3 session for managing credentials and region
    session_kwargs = {}
    if aws_region:
        session_kwargs["region_name"] = aws_region
    if aws_profile:
        session_kwargs["profile_name"] = aws_profile

    session = aioboto3.Session(aws_access_key_id=key_id, aws_secret_access_key=key, **session_kwargs)
    downloaded_count = 0
    failed_count = 0

    # Initialize tqdm progress bar
    pbar = tqdm.tqdm(total=total_files_to_attempt, unit="file", desc=desc, smoothing=0.1)

    async with session.client("s3") as s3_client:
        for i in range(0, total_files_to_attempt, batch_size):
            current_batch_files = files_to_download[i : i + batch_size]
            batch_tasks = []

            for local_file_path, s3_key in current_batch_files:
                task = asyncio.create_task(
                    download_file_async(
                        s3_client,
                        local_file_path,
                        bucket,
                        s3_key,
                        failure_log_path,
                        failure_log_lock,  # Pass the lock to each task
                    )
                )
                batch_tasks.append(task)

            # Wait for the current batch of uploads to complete
            results = await asyncio.gather(
                *batch_tasks
            )  # gather runs them concurrently

            # Update counts and progress bar based on results
            batch_success = sum(1 for r in results if r is True)
            batch_fail = len(results) - batch_success
            downloaded_count += batch_success
            failed_count += batch_fail

            pbar.update(
                len(results)
            )  # Update progress bar by the number of tasks completed
            pbar.set_postfix(
                succeeded=downloaded_count, failed=failed_count, refresh=True
            )  # Update stats

    pbar.close()  # Close the progress bar
    logging.info(
        f"Download processing complete. Succeeded: {downloaded_count}, Failed: {failed_count}"
    )
    return downloaded_count, failed_count


async def main():
    with open('images_to_download.json') as f:
        images_to_download = json.load(f)

    files_to_download = list(map(lambda e: (Path(f'downloaded_images/{e.get('imageId')}.jpg'), f'counti-images/{e.get('batchId')}/{e.get('imageId')}.jpg'), images_to_download))

    os.makedirs('downloaded_images', exist_ok=True)

    await process_download_batches(
        files_to_download=files_to_download,
        bucket='',
        aws_region=None,
        aws_profile=None,
        key_id="",
        key="",
        batch_size=200,
        failure_log_path=Path('failures.json'),
    )

if __name__ == '__main__':
    asyncio.run(main())
