import gi 
import sys
from time import sleep
from pathlib import Path
import supervision as sv
from subprocess import Popen, PIPE
import socketio
import base64
import json
from turbojpeg import TurboJPEG
import tqdm
import os

gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
from gi.repository import Gst, GstPbutils

Gst.init(sys.argv)

def get_file_duration(file: Path) -> float:
    discoverer = GstPbutils.Discoverer()
    asset_info = discoverer.discover_uri(str(file.as_uri()))
    duration_in_seconds = asset_info.get_duration() / 1_000_000_000
    return duration_in_seconds

def start_detection_process():
    process = Popen(['python', 'counter_app.py'], stderr=PIPE)
    return process


def main():
    src_folder = '/home/ammanz/Projects/RECYCLOROBO.ai/AIContainerCounter/Backend/counting-machine-test-videos'
    dest_folder = '/home/ammanz/Projects/RECYCLOROBO.ai/AIContainerCounter/Backend/counting-machine-test-output-videos-3'
    os.makedirs(dest_folder, exist_ok=True)
    expected_count = 30
    results = []
    jpeg = TurboJPEG()
    client = socketio.Client()
    frame_time_metrics = {}
    counting_result = {}
    frames = []
    @client.on('detection_event')
    def on_detection_event(message):
        counting_result['total_in'] = message.get('total_in')
        counting_result['total_out'] = message.get('total_out')
        counting_result['class_wise_count'] = message.get('class_wise_count')
        frames.append(message.get('encoded_frame'))
    @client.on('frame_time')
    def on_frame_time(message):
        nonlocal frame_time_metrics
        frame_time_metrics = message

    video_files = os.listdir(src_folder)
    video_files.sort()
    for test_video_file_name in video_files:
        file = f'{src_folder}/{test_video_file_name}'
        video_duration = get_file_duration(Path(file))
        print(f"video_duration in seconds: {video_duration}")
        pipeline = Gst.parse_launch(f"""filesrc name="file-source" location="{file}" ! decodebin ! videoconvert ! avenc_mjpeg ! v4l2sink device=/dev/video2""")
        print('Playing Video')
        pipeline.set_state(Gst.State.PLAYING)
        counter_app_process = start_detection_process()
        client.connect(url='http://localhost:5000', transports=['websocket'], namespaces=['/'], retry=True)
        sleep(video_duration)
        pipeline.set_state(Gst.State.NULL)
        print('Disconnecting socketio client...')
        client.disconnect()
        counter_app_process.terminate()
        print('waiting for counter app process to terminate')
        counter_app_process.wait()

        print(counting_result)
        counting_result['file'] = test_video_file_name
        counting_result['accuracy'] = counting_result.get('total_out') / expected_count * 100
        counting_result['frame_time_metrics'] = frame_time_metrics
        results.append(counting_result)
        with sv.VideoSink(f'{dest_folder}/{test_video_file_name.split('.')[0]}.mp4', sv.VideoInfo(height=1080, width=1920, fps=round(frame_time_metrics.get('avg_fps')), total_frames=len(frames))) as video_sink:
            with tqdm.tqdm(frames, f'saving output frames to file for {test_video_file_name}') as pbar:
                for encoded_frame in frames:
                    base64_decoded = base64.b64decode(encoded_frame)
                    decoded_frame = jpeg.decode(base64_decoded)
                    video_sink.write_frame(decoded_frame)
                    pbar.update()
        frame_time_metrics = {}
        counting_result = {}
        frames = []

        overall_results = {
            'overall_accuracy': sum(list(map(lambda e: e.get('total_out'), results))) / (len(results) * expected_count) * 100,
            'overall_fps': sum(list(map(lambda e: e.get('frame_time_metrics').get('avg_fps'), results))) / len(results),
            'results': results
        }

        with open(f'{dest_folder}/results.json', 'w') as f:
            json.dump(overall_results, f, indent=4)



main()