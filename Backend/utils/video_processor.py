import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
from utils.sqlmodel_db import get_all_batches_from_day, Batch, engine
from sqlmodel import Session
import datetime
import tqdm
import boto3
from botocore.exceptions import BotoCoreError, ClientError
import threading
import os
import subprocess

Gst.init(None)

def get_all_unprocessed_batches_for_day(day: datetime.datetime):

    start = datetime.datetime(day.year, day.month, day.day)
    end = start + datetime.timedelta(days=1)

    batches = Batch.select().where((Batch.time_submitted > start) & (Batch.time_submitted < end)).order_by(Batch.time_submitted.desc())
    
    return list(batches)

def get_total_frames_ffprobe(path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-count_frames",
        "-show_entries", "stream=nb_read_frames",
        "-of", "csv=p=0",
        path
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        return int(output)
    except Exception as e:
        print(f"ffprobe error: {e}")
        return -1

def compress_video(input_path, output_path, progress_callback=None):
    loop = GLib.MainLoop()
    successful = False
    current_frame = 0

    # Create pipeline string
    pipeline_str = f"""
        filesrc location={input_path} !
        queue max-size-buffers=6 max-size-bytes=0 max-size-time=0 !
        decodebin name=dec !
        queue max-size-buffers=6 max-size-bytes=0 max-size-time=0 !
        videoconvert name=conv !
        queue max-size-buffers=6 max-size-bytes=0 max-size-time=0 !
        x264enc tune=zerolatency quantizer=18 speed-preset=9 !
        queue max-size-buffers=6 max-size-bytes=0 max-size-time=0 !
        mp4mux !
        queue max-size-buffers=6 max-size-bytes=0 max-size-time=0 !
        filesink location={output_path}
    """

    # Parse pipeline
    pipeline = Gst.parse_launch(pipeline_str)
    bus = pipeline.get_bus()
    bus.add_signal_watch()

    # Connect to the sink pad of videoconvert to count frames
    conv = pipeline.get_by_name("conv")
    sinkpad = conv.get_static_pad("sink")

    def on_probe(pad, info):
        nonlocal current_frame
        if info.type & Gst.PadProbeType.BUFFER:
            current_frame += 1
            if progress_callback:
                progress_callback(1, current_frame)
        return Gst.PadProbeReturn.OK

    sinkpad.add_probe(Gst.PadProbeType.BUFFER, on_probe)

    def on_message(bus, message):
        nonlocal successful
        t = message.type
        if t == Gst.MessageType.EOS:
            successful = True
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Pipeline error: {err.message}")
            print(f"Debug info: {debug}")
            loop.quit()

    # Connect bus message handler
    bus.connect("message", on_message)

    # Start pipeline
    pipeline.set_state(Gst.State.PLAYING)

    # Run the loop until EOS or ERROR
    try:
        loop.run()
    except KeyboardInterrupt:
        print("Interrupted.")
        pipeline.send_event(Gst.Event.new_eos())
        loop.quit()

    # Cleanup
    pipeline.set_state(Gst.State.NULL)
    return successful

class UploadProgress:
    def __init__(self, filename, callback=None):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()
        self._callback = callback

    def __call__(self, bytes_amount):
        with self._lock:
            self._seen_so_far += bytes_amount
            if self._callback:
                self._callback(bytes_amount, self._seen_so_far)

def upload_to_s3(file_path, bucket, key, access_key=None, secret_key=None, progress_callback=None):
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )

        progress = UploadProgress(file_path, progress_callback)

        s3.upload_file(file_path, bucket, key, Callback=progress)
        return True
    except (BotoCoreError, ClientError) as e:
        print(f"[S3 Upload Error] {e}")
        return False

def process_batch(
        batch: Batch,
        batch_index: int,
        num_of_batches: int,
        aws_s3_bucket: str,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        aws_key_prefix: str
    ):

    print(f'getting total number of frames for {batch.id}')
    total_frames = get_total_frames_ffprobe(f'data/annotated/{batch.id}.avi')
    with tqdm.tqdm(desc=f'Processing {batch_index + 1}/{num_of_batches} {batch.id}', total=total_frames) as pbar:
        def on_progress(new_progress, current_progress):
            pbar.update(new_progress)
        compress_video(f'data/annotated/{batch.id}.avi', f'data/annotated/{batch.id}.mp4', progress_callback=on_progress)
    batch.compressed_annotated_video = True
    with Session(engine) as session:
        session.merge(batch)
        session.commit()

        file_size_bytes = os.path.getsize(f'data/annotated/{batch.id}.mp4')
        with tqdm.tqdm(desc=f'Uploading {batch_index + 1}/{num_of_batches} {batch.id}', total=(file_size_bytes / 1_000_000)) as pbar:
            def on_progress(new_progress, current_progress):
                pbar.update(new_progress / 1_000_000)
            upload_to_s3(
                f'data/annotated/{batch.id}.mp4',
                progress_callback=on_progress,
                key=f'{aws_key_prefix}/{batch.id}/annotated.mp4',
                bucket=aws_s3_bucket,
                access_key=aws_access_key_id,
                secret_key=aws_secret_access_key
            )
        batch.uploaded_annotated_video_to_s3 = True
        session.merge(batch)
        session.commit()

if __name__ == '__main__':
    aws_access_key_id=""
    aws_secret_access_key=""
    aws_s3_bucket=""
    batches = get_all_batches_from_day(datetime.datetime.now())
    num_of_batches = len(batches)
    for batch_index, batch in enumerate(batches):
        process_batch(
            batch=batch,
            batch_index=batch_index,
            num_of_batches=num_of_batches,
            aws_s3_bucket=aws_s3_bucket,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_key_prefix='counti-videos'
        )