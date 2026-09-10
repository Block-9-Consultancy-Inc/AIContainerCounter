# upload_batches_enhanced.py
import asyncio
import logging
import os
import argparse
from pathlib import Path
import time
import uuid
import json
import datetime

import aioboto3
import aiofiles
from botocore.exceptions import ClientError
import sys

# Assuming models.py is in the same directory or accessible via PYTHONPATH
try:
    from sqlmodel_db import Batch, MultiContainerImage, engine
    from sqlmodel import Session, select
except ImportError as e:
    logging.error(f"ERROR: Cannot import 'sqlmodel_db'. Make sure 'sqlmodel_db.py' is in the same directory or your PYTHONPATH. Error: {e}")
    exit(1)

# Third-party library for progress bars
try:
    from tqdm.asyncio import tqdm  # Use tqdm's asyncio-compatible version
except ImportError:
    logging.error("tqdm library not found. Please install it: pip install tqdm")
    exit(1)

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
EXPECTED_EXTENSION = ".jpg"  # Define the expected local file extension
DEFAULT_FAILURE_LOG = "failed_uploads.jsonl"  # Use .jsonl for JSON Lines format

# --- Core Functions ---


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


async def upload_file_async(
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
    if not local_path.is_file():
        error_message = f"Local file not found: {local_path}"
        logging.warning(error_message)  # Log as warning, it's expected sometimes
        await log_failure(
            failure_log_path, failure_log_lock, local_path, s3_key, error_message
        )
        return False
    try:
        async with aiofiles.open(local_path, mode="rb") as f:
            content = await f.read()
        await s3_client.put_object(Bucket=bucket, Key=s3_key, Body=content)
        # Success, no need to log anything here for failures
        # logging.info(f"Successfully uploaded {local_path} to s3://{bucket}/{s3_key}") # Reduce log noise
        return True
    except ClientError as e:
        error_message = f"S3 ClientError: {e}"
        logging.error(
            f"Failed upload {local_path} to s3://{bucket}/{s3_key}: {error_message}"
        )
        await log_failure(
            failure_log_path, failure_log_lock, local_path, s3_key, error_message
        )
        return False
    except FileNotFoundError:  # Should be caught by the check above, but good failsafe
        error_message = f"FileNotFoundError during read: {local_path}"
        logging.error(error_message)
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


async def process_upload_batches(
    files_to_upload: list[tuple[Path, str]],
    bucket: str,
    aws_region: str | None,
    aws_profile: str | None,
    key: str,
    key_id: str,
    batch_size: int,
    failure_log_path: Path,
    desc: str = "Uploading Files",  # Description for tqdm
):
    """
    Processes a list of file uploads asynchronously in batches with progress bar and failure logging.
    """
    total_files_to_attempt = len(files_to_upload)
    if not total_files_to_attempt:
        logging.info("No files provided for upload processing.")
        return 0, 0  # No successes, no failures

    logging.info(f"Starting asynchronous upload of {total_files_to_attempt} files...")

    # Create a lock for writing to the failure log file
    failure_log_lock = asyncio.Lock()

    # Use aioboto3 session for managing credentials and region
    session_kwargs = {}
    if aws_region:
        session_kwargs["region_name"] = aws_region
    if aws_profile:
        session_kwargs["profile_name"] = aws_profile

    session = aioboto3.Session(aws_access_key_id=key_id, aws_secret_access_key=key, **session_kwargs)
    uploaded_count = 0
    failed_count = 0

    # Initialize tqdm progress bar
    pbar = tqdm(total=total_files_to_attempt, unit="file", desc=desc, smoothing=0.1)

    async with session.client("s3") as s3_client:
        for i in range(0, total_files_to_attempt, batch_size):
            current_batch_files = files_to_upload[i : i + batch_size]
            batch_tasks = []

            for local_file_path, s3_key in current_batch_files:
                task = asyncio.create_task(
                    upload_file_async(
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
            uploaded_count += batch_success
            failed_count += batch_fail

            pbar.update(
                len(results)
            )  # Update progress bar by the number of tasks completed
            pbar.set_postfix(
                succeeded=uploaded_count, failed=failed_count, refresh=True
            )  # Update stats

    pbar.close()  # Close the progress bar
    logging.info(
        f"Upload processing complete. Succeeded: {uploaded_count}, Failed: {failed_count}"
    )
    return uploaded_count, failed_count


async def discover_files_from_db(
    db_path: str, src_dir: str, s3_prefix: str = ""
) -> tuple[list[tuple[Path, str]], dict]:
    """
    Connects to the DB, finds all batches and their images, checks local directories,
    and returns a list of (local_path, s3_key) tuples and discovery stats.
    """
    source_base_path = Path(src_dir).resolve()
    master_files_to_upload = []
    stats = {
        "total_batches_found": 0,
        "batches_processed": 0,
        "batches_skipped_no_dir": 0,
        "total_images_found_in_db": 0,
        "files_queued_for_upload": 0,
        "local_files_missing_precheck": 0,
    }

    logging.info("--- Starting Database Discovery Phase ---")
    try:
        # SQLModel uses sessions, no need to manually connect

        with Session(engine) as session:
            all_batches = list(session.exec(select(Batch).where(Batch.time_submitted > datetime.datetime(2025, 8, 15)).order_by(Batch.time_submitted.desc())).all())
            stats["total_batches_found"] = len(all_batches)
            logging.info(
                f"Found {stats['total_batches_found']} Batch records in the database."
            )

            if not all_batches:
                logging.warning("No batches found in the database.")
                return [], stats  # Return empty list and initial stats

            for batch_record in tqdm(all_batches, desc="Discovering Batches", unit="batch"):
                batch_uuid_str = str(batch_record.id)
                # logging.debug(f"Processing Batch ID: {batch_uuid_str}") # Reduce noise

                local_batch_dir = source_base_path / batch_uuid_str
                if not local_batch_dir.is_dir():
                    logging.warning(
                        f"Source directory for batch {batch_uuid_str} not found at {local_batch_dir}. Skipping."
                    )
                    stats["batches_skipped_no_dir"] += 1
                    continue

                # Get related MultiContainerImages for this batch
                images_query = select(MultiContainerImage).where(MultiContainerImage.batch_id == batch_record.id)
                image_records = list(session.exec(images_query).all())
                batch_image_count = len(image_records)
                stats["total_images_found_in_db"] += batch_image_count

                if not image_records:
                    # logging.info(f"No image records found for Batch ID {batch_uuid_str}.")
                    stats["batches_processed"] += 1  # Count as processed
                    continue

                # logging.debug(f"Found {batch_image_count} image records for batch {batch_uuid_str}.")
                files_added_for_batch = 0
                for image in image_records:
                    local_filename = f"{image.id}.{image.index}{EXPECTED_EXTENSION}"
                    local_file_path = local_batch_dir / "multi_container_images" / local_filename
                    s3_object_key = (
                        f"{s3_prefix}{batch_uuid_str}/{image.id}{EXPECTED_EXTENSION}"
                    )

                    # Optional pre-check (upload_file_async will handle it anyway, but can provide early stats)
                    if not local_file_path.is_file():
                        logging.debug(
                            f"Local file missing during discovery: {local_file_path}"
                        )
                        stats["local_files_missing_precheck"] += 1
                        # Still add it to the list; upload_file_async will log it to failure file
                    master_files_to_upload.append((local_file_path, s3_object_key))
                    files_added_for_batch += 1

                # logging.debug(f"Added {files_added_for_batch} file paths for batch {batch_uuid_str}.")
                stats["batches_processed"] += 1

    except Exception as e:
        logging.error(f"Database error during discovery: {e}", exc_info=True)
        # Depending on severity, you might want to re-raise or return partial results
        raise  # Re-raise to stop execution if DB fails critically
    finally:
        # SQLModel sessions are automatically managed
        pass

    stats["files_queued_for_upload"] = len(master_files_to_upload)
    logging.info("--- Database Discovery Phase Complete ---")
    logging.info(f"Discovery Summary: {stats}")
    return master_files_to_upload, stats


async def load_failures_from_log(failure_log_path: Path) -> list[tuple[Path, str]]:
    """Reads a JSON Lines failure log and returns a list of (local_path, s3_key) tuples."""
    files_to_retry = []
    if not failure_log_path.is_file():
        logging.error(f"Failure log file not found: {failure_log_path}")
        return []

    logging.info(f"Loading failed uploads from: {failure_log_path}")
    try:
        async with aiofiles.open(failure_log_path, mode="r", encoding="utf-8") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    local_path_str = entry.get("local_path")
                    s3_key = entry.get("s3_key")
                    if local_path_str and s3_key:
                        files_to_retry.append((Path(local_path_str), s3_key))
                    else:
                        logging.warning(
                            f"Skipping invalid entry in failure log: {line}"
                        )
                except json.JSONDecodeError:
                    logging.warning(f"Skipping non-JSON line in failure log: {line}")
                except Exception as e:
                    logging.warning(
                        f"Error processing line '{line}' from failure log: {e}"
                    )

    except Exception as e:
        logging.error(f"Error reading failure log file {failure_log_path}: {e}")
        return []  # Return empty list on error

    logging.info(
        f"Loaded {len(files_to_retry)} entries to retry from {failure_log_path}"
    )
    return files_to_retry


# --- Main Execution Logic ---
async def main():
    parser = argparse.ArgumentParser(
        description="Uploads images for batches from a Peewee DB to S3 with progress, failure logging, and retry."
    )
    # Mode selection arguments
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--discover-and-upload",
        action="store_true",
        help="Discover all batches from DB and upload their files.",
    )
    mode_group.add_argument(
        "--retry-from",
        metavar="FAILURE_LOG_PATH",
        help="Retry uploads listed in the specified failure log file (JSON Lines format).",
    )

    # Common arguments
    parser.add_argument(
        "--db-path",
        help="Path to the SQLite database file (required for --discover-and-upload).",
    )
    parser.add_argument(
        "--src-dir",
        help="Base local directory for batch subdirectories (required for --discover-and-upload).",
    )
    parser.add_argument("-b", "--bucket", required=True, help="Name of the S3 bucket.")
    parser.add_argument(
        "--failure-log",
        default=DEFAULT_FAILURE_LOG,
        help=f"Path to the JSON Lines file for logging failures (default: {DEFAULT_FAILURE_LOG}).",
    )

    # AWS and Upload configuration arguments
    parser.add_argument(
        "-r",
        "--region",
        default=None,
        help="AWS region (e.g., 'us-east-1'). Uses default from env/config if omitted.",
    )
    parser.add_argument(
        "-p",
        "--profile",
        default=None,
        help="AWS profile name to use (from ~/.aws/credentials).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of files to upload concurrently in each S3 upload batch.",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Optional S3 prefix (folder path) to upload files into within the bucket.",
    )

    parser.add_argument('--key')
    parser.add_argument("--key-id")

    args = parser.parse_args()

    # --- Argument Validation ---
    if args.discover_and_upload:
        if not args.db_path or not args.src_dir:
            parser.error(
                "--db-path and --src-dir are required when using --discover-and-upload."
            )
        if not Path(args.db_path).is_file():
            logging.error(f"Database file not found: {args.db_path}")
            return
        if not Path(args.src_dir).is_dir():
            logging.error(f"Base source directory not found: {args.src_dir}")
            return
    elif args.retry_from:
        if not Path(args.retry_from).is_file():
            logging.error(f"Retry failure log file not found: {args.retry_from}")
            return
        # When retrying, use the provided log path as the source, but log *new* failures to the --failure-log path
        logging.info(
            f"Retry mode activated. Reading from '{args.retry_from}'. New failures will be logged to '{args.failure_log}'."
        )

    # --- Determine files to process ---
    files_to_process = []
    overall_start_time = time.time()
    failure_log_path = Path(args.failure_log)
    s3_prefix = args.prefix.strip("/") + "/" if args.prefix.strip() else ""

    if args.discover_and_upload:
        try:
            files_to_process, _ = await discover_files_from_db(
                db_path=args.db_path, src_dir=args.src_dir, s3_prefix=s3_prefix
            )
        except Exception as e:
            logging.error(f"Failed during discovery phase: {e}")
            return  # Stop if discovery fails

    elif args.retry_from:
        files_to_process = await load_failures_from_log(Path(args.retry_from))
        # Note: When retrying, we might want a different failure log or overwrite strategy.
        # Current behavior: retries failed items from retry_from, logs *new* failures during retry to failure_log.
        if failure_log_path == Path(args.retry_from):
            logging.warning(
                f"Failure log '{args.failure_log}' is the same as retry source '{args.retry_from}'. New failures will be appended."
            )
        # Optional: Clear the failure log before retrying if desired
        # if failure_log_path.exists():
        #     try:
        #         failure_log_path.unlink()
        #         logging.info(f"Cleared existing failure log: {failure_log_path}")
        #     except OSError as e:
        #         logging.error(f"Could not clear existing failure log {failure_log_path}: {e}")

    # --- Execute Upload Processing ---
    if not files_to_process:
        logging.info("No files identified for upload or retry.")
    else:
        mode_desc = (
            "Retrying Failed Files" if args.retry_from else "Uploading Discovered Files"
        )
        succeeded, failed = await process_upload_batches(
            files_to_upload=files_to_process,
            bucket=args.bucket,
            aws_region=args.region,
            aws_profile=args.profile,
            key=args.key,
            key_id=args.key_id,
            batch_size=args.batch_size,
            failure_log_path=failure_log_path,
            desc=mode_desc,
        )

        # --- Final Summary ---
        overall_duration = time.time() - overall_start_time
        logging.info("=" * 30)
        logging.info("Overall Execution Summary:")
        if args.discover_and_upload:
            logging.info(f"Mode: Discover and Upload")
        elif args.retry_from:
            logging.info(f"Mode: Retry from {args.retry_from}")

        logging.info(f"Total files attempted: {len(files_to_process)}")
        logging.info(f"Successfully uploaded: {succeeded}")
        logging.info(f"Failed/Skipped uploads: {failed}")
        logging.info(f"Failures logged to: {failure_log_path}")
        logging.info(f"Total duration: {overall_duration:.2f} seconds")
        logging.info("=" * 30)


if __name__ == "__main__":
    # Ensure compatibility if running on Windows with ProactorEventLoop
    # if os.name == 'nt':
    #      asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()) # Usually not needed for modern Python 3.8+

    # Check if models.py is importable before running asyncio
    try:
        import sqlmodel_db
    except ImportError:
        print(
            "ERROR: Cannot import 'sqlmodel_db'. Make sure 'sqlmodel_db.py' is in the same directory or your PYTHONPATH.",
            file=sys.stderr,
        )
        sys.exit(1)  # Use sys.exit here as logging might not be configured yet
    except Exception as e:
        print(
            f"ERROR: An unexpected error occurred during initial import check: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(main())
