import gi 
import sys
from time import sleep
from pathlib import Path
import supervision as sv
from subprocess import Popen
import socketio
import base64
import json
from turbojpeg import TurboJPEG
import tqdm
import os

gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
from gi.repository import Gst, GstPbutils

Gst.init(sys.argv[0:1])

ITERATIONS_PER_TEST = 3

def get_file_duration(file: Path) -> float:
    discoverer = GstPbutils.Discoverer()
    asset_info = discoverer.discover_uri(str(file.as_uri()))
    duration_in_seconds = asset_info.get_duration() / 1_000_000_000
    return duration_in_seconds

def start_detection_process(dotenv_path: str):
    process = Popen(['python', 'counter_app.py', dotenv_path])
    return process

def sleep_with_progress(duration: float, description: str):
    remaining_duration = duration
    with tqdm.tqdm(total=duration, desc=description) as pbar:
        while remaining_duration > 0:
            time_to_sleep = 1 if remaining_duration >= 1 else remaining_duration
            sleep(time_to_sleep)
            remaining_duration -= time_to_sleep
            pbar.update(time_to_sleep)



def counter_app_tester(src_folder: str, dest_folder: str, env_folder: str):
    expected_count = 30
    jpeg = TurboJPEG()
    client = socketio.Client()

    current_test_iteration_frame_time_metrics = {}
    current_test_iteration_counting_result = {}
    current_test_iteration_frames = []
    @client.on('detection_event')
    def on_detection_event(message):
        current_test_iteration_counting_result['total_in'] = message.get('total_in')
        current_test_iteration_counting_result['total_out'] = message.get('total_out')
        current_test_iteration_counting_result['class_wise_count'] = message.get('class_wise_count')
        current_test_iteration_frames.append(message.get('encoded_frame'))
    @client.on('frame_time')
    def on_frame_time(message):
        nonlocal current_test_iteration_frame_time_metrics
        current_test_iteration_frame_time_metrics = message

    video_files = os.listdir(src_folder)
    video_files.sort()
    num_of_video_files = len(video_files)

    dotenv_files = os.listdir(env_folder)
    dotenv_files.sort()
    num_of_dotenv_files = len(dotenv_files)

    overall_results = []

    for env_index, env in enumerate(dotenv_files):
        current_env_overall_results = {
            'env': env,
            'overall_accuracy': 0,
            'overall_fps': 0,
        }
        overall_results.append(current_env_overall_results)
        current_env_results = []
        current_env_path = f'{env_folder}/{env}'
        current_dest_folder = f'{dest_folder}/{env.split('.')[0]}'
        os.makedirs(current_dest_folder, exist_ok=True)
        for test_video_index, test_video_file_name in enumerate(video_files):
            file = f'{src_folder}/{test_video_file_name}'
            video_duration = get_file_duration(Path(file))
            for test_video_iteration in range(ITERATIONS_PER_TEST):
                pipeline = Gst.parse_launch(f"""filesrc name="file-source" location="{file}" ! decodebin ! videoconvert ! avenc_mjpeg ! v4l2sink device=/dev/video2""")
                print(f'Starting test iteration #{test_video_iteration+1}/{ITERATIONS_PER_TEST} of {test_video_file_name} {test_video_index+1}/{num_of_video_files} for env {env} {env_index+1}/{num_of_dotenv_files}')
                pipeline.set_state(Gst.State.PLAYING)
                counter_app_process = start_detection_process(current_env_path)
                client.connect(url='http://localhost:5000', transports=['websocket'], namespaces=['/'], retry=True)
                sleep_with_progress(video_duration, f'Running test iteration #{test_video_iteration+1}/{ITERATIONS_PER_TEST} of {test_video_file_name} {test_video_index+1}/{num_of_video_files} for env {env} {env_index+1}/{num_of_dotenv_files}')
                pipeline.set_state(Gst.State.NULL)
                print('Disconnecting socketio client...')
                client.disconnect()
                counter_app_process.terminate()
                print('waiting for counter app process to terminate')
                counter_app_process.wait()

                print(current_test_iteration_counting_result)
                current_test_iteration_counting_result['file'] = test_video_file_name
                current_test_iteration_counting_result['iteration'] = test_video_iteration + 1
                current_test_iteration_counting_result['accuracy'] = current_test_iteration_counting_result.get('total_out') / expected_count * 100
                current_test_iteration_counting_result['frame_time_metrics'] = current_test_iteration_frame_time_metrics
                current_env_results.append(current_test_iteration_counting_result)
                with sv.VideoSink(f'{current_dest_folder}/{test_video_file_name.split('.')[0]}-{test_video_iteration+1}.mp4', sv.VideoInfo(height=1080, width=1920, fps=round(current_test_iteration_frame_time_metrics.get('avg_fps')), total_frames=len(current_test_iteration_frames))) as video_sink:
                    with tqdm.tqdm(current_test_iteration_frames, f'saving output frames to file for iteration #{test_video_iteration+1}/{ITERATIONS_PER_TEST} of {test_video_file_name} {test_video_index+1}/{num_of_video_files} for env {env} {env_index+1}/{num_of_dotenv_files}') as pbar:
                        for encoded_frame in current_test_iteration_frames:
                            base64_decoded = base64.b64decode(encoded_frame)
                            decoded_frame = jpeg.decode(base64_decoded)
                            video_sink.write_frame(decoded_frame)
                            pbar.update()

                current_env_overall_results = {
                    'env': env,
                    'overall_accuracy': sum(list(map(lambda e: e.get('total_out'), current_env_results))) / (len(current_env_results) * expected_count) * 100,
                    'overall_fps': sum(list(map(lambda e: e.get('frame_time_metrics').get('avg_fps'), current_env_results))) / len(current_env_results),
                }

                with open(f'{current_dest_folder}/results.json', 'w') as f:
                    json.dump({**current_env_overall_results, 'results': current_env_results}, f, indent=4)

                overall_results[len(overall_results) - 1] = current_env_overall_results

                with open(f'{dest_folder}/overall_results.json', 'w') as f:
                    json.dump(overall_results, f, indent=4)

                current_test_iteration_frame_time_metrics = {}
                current_test_iteration_counting_result = {}
                current_test_iteration_frames = []

if __name__ == '__main__':
    src_folder = sys.argv[1]
    dest_folder = sys.argv[2]
    env_folder = sys.argv[3]
    counter_app_tester(src_folder, dest_folder, env_folder)