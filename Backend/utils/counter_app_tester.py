import gi 
import sys
from time import sleep, perf_counter
from pathlib import Path
import supervision as sv
from subprocess import Popen, DEVNULL
from threading import Thread
import socketio
import base64
import json
from turbojpeg import TurboJPEG
import tqdm
import os
from dotenv import dotenv_values

gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
from gi.repository import Gst, GstPbutils

Gst.init(sys.argv[0:1])

ITERATIONS_PER_TEST = 3
VIRTUAL_CAMERA='/dev/video0'

def get_file_duration(file: Path) -> float:
    discoverer = GstPbutils.Discoverer()
    asset_info = discoverer.discover_uri(str(file.as_uri()))
    duration_in_seconds = asset_info.get_duration() / 1_000_000_000
    
    return duration_in_seconds

def start_video_stream_to_v4l2loopback_dummy_device(test_video_file_path: str, loop = False):
    if loop:
        process = Popen(['ffmpeg', '-stream_loop', '-1', '-re', '-i', test_video_file_path, '-c:v', 'copy', '-f', 'v4l2', VIRTUAL_CAMERA], stdout=DEVNULL, stderr=DEVNULL)
    else:
        process = Popen(['ffmpeg', '-re', '-i', test_video_file_path, '-c:v', 'copy', '-f', 'v4l2', VIRTUAL_CAMERA], stdout=DEVNULL, stderr=DEVNULL)
    return process


def start_detection_process(dotenv_path: str):
    process = Popen(['python', 'counter_app.py', dotenv_path, 'test'], stdout=DEVNULL, stderr=DEVNULL)
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
    test_starting_time = perf_counter()
    jpeg = TurboJPEG()
    client = socketio.Client()

    current_test_iteration_frame_time_metrics = {}
    current_test_iteration_counting_result = {
        'count': 0,
        'can_count': 0,
        'plastic_count': 0,
        'drinkbox_count': 0,
        'gabletop_count': 0,
        'pouch_count': 0
    }
    current_test_iteration_frames = []

    client_initializing = True
    batch_done = False
    @client.on('detection_event')
    def on_detection_event(message):
        # print(f'detection event with count: {message.get('count')}')
        current_test_iteration_counting_result['count'] = max(message.get('count'), current_test_iteration_counting_result['count'])
        current_test_iteration_counting_result['can_count'] = max(message.get('can_count'), current_test_iteration_counting_result['can_count'])
        current_test_iteration_counting_result['plastic_count'] = max(message.get('plastic_count'), current_test_iteration_counting_result['plastic_count'])
        current_test_iteration_counting_result['drinkbox_count'] = max(message.get('drinkbox_count'), current_test_iteration_counting_result['drinkbox_count'])
        current_test_iteration_counting_result['gabletop_count'] = max(message.get('gabletop_count'), current_test_iteration_counting_result['gabletop_count'])
        current_test_iteration_counting_result['pouch_count'] = max(message.get('pouch_count'), current_test_iteration_counting_result['pouch_count'])
        current_test_iteration_frames.append(message.get('encoded_frame'))
    @client.on('frame_time')
    def on_frame_time(message):
        nonlocal current_test_iteration_frame_time_metrics
        if message.get('num_of_frames', 0) >= current_test_iteration_frame_time_metrics.get('num_of_frames', 0):
            current_test_iteration_frame_time_metrics = message
    
    @client.on('batches_state')
    def on_batches_state(message):
        nonlocal batch_done
        if not client_initializing:
            batch_done = True


    dotenv_files = os.listdir(env_folder)
    dotenv_files.sort()
    num_of_dotenv_files = len(dotenv_files)

    overall_results = []

    for env_index, env in enumerate(dotenv_files):
        current_env_start = perf_counter()
        current_env_overall_results = {
            'env': env,
            'overall_accuracy': 0,
            'overall_fps': 0,
        }
        overall_results.append(current_env_overall_results)
        current_env_results = []
        current_env_path = f'{env_folder}/{env}'
        current_env_values = dotenv_values(current_env_path)
        current_env_height, current_env_width = current_env_values.get('HEIGHT', '1080'), current_env_values.get('WIDTH', '1920')
        current_env_name = env.split('.')[0]

        print('initializing counter app with empty frames')
        intro_file = f'{src_folder}/intro.avi'
        video_duration = get_file_duration(Path(intro_file))
        video_playback_process = start_video_stream_to_v4l2loopback_dummy_device(intro_file, loop=True)
        waiting_thread = Thread(target=sleep_with_progress, args=[video_duration + 5, f'Waiting for intro video to finish to initialize counter app'])
        counter_app_process = start_detection_process(current_env_path)
        waiting_thread.start()
        client.connect(url='http://localhost:5000', transports=['polling'], namespaces=['/'], retry=True)
        waiting_thread.join()
        video_playback_process.terminate()
        video_playback_process.wait()
        client_initializing = False

        for batch in os.listdir(src_folder):
            with open(f'{src_folder}/{batch}/breakdown.json') as f:
                expected_counts = json.load(f)
            video_files = os.listdir(f'{src_folder}/{batch}')
            video_files.sort()
            num_of_video_files = len(video_files)
            current_dest_folder = f'{dest_folder}/{current_env_name}/{batch}'
            os.makedirs(current_dest_folder, exist_ok=True)
            for test_video_index, test_video_file_name in enumerate(video_files):
                if test_video_file_name.endswith('.json'):
                    continue
                file = f'{src_folder}/{batch}/{test_video_file_name}'
                print(f'file: {file}')
                video_duration = get_file_duration(Path(file))
                for test_video_iteration in range(ITERATIONS_PER_TEST):
                    current_iteration_start = perf_counter()
                    video_playback_process = start_video_stream_to_v4l2loopback_dummy_device(file)
                    waiting_thread = Thread(target=sleep_with_progress, args=[video_duration + 2, f'Running test iteration #{test_video_iteration+1}/{ITERATIONS_PER_TEST} of {test_video_file_name} in {batch} {test_video_index+1}/{num_of_video_files} for env {env} {env_index+1}/{num_of_dotenv_files}'])
                    waiting_thread.start()
                    waiting_thread.join()
                    
                    video_playback_process = start_video_stream_to_v4l2loopback_dummy_device(intro_file, loop=True)
                    client.emit('reset-count', 'reset-count')
                    while not batch_done:
                        print('batch not done yet')
                        sleep(0.25)
                    batch_done = False
                    video_playback_process.terminate()
                    video_playback_process.wait()

                    print(current_test_iteration_counting_result)
                    current_test_iteration_counting_result['file'] = test_video_file_name
                    current_test_iteration_counting_result['iteration'] = test_video_iteration + 1
                    current_test_iteration_counting_result['accuracy'] = max(1 - ((abs(current_test_iteration_counting_result.get('count') - expected_counts['total'])) / expected_counts['total']), 0) * 100
                    current_test_iteration_counting_result['can_accuracy'] = max(1 - ((abs(current_test_iteration_counting_result.get('can_count') - expected_counts['can'])) / expected_counts['can']), 0) * 100
                    current_test_iteration_counting_result['plastic_accuracy'] = max(1 - ((abs(current_test_iteration_counting_result.get('plastic_count') - expected_counts['plastic'])) / expected_counts['plastic']), 0) * 100
                    current_test_iteration_counting_result['drinkbox_accuracy'] = max(1 - ((abs(current_test_iteration_counting_result.get('drinkbox_count') - expected_counts['drinkbox'])) / expected_counts['drinkbox']), 0) * 100
                    current_test_iteration_counting_result['gabletop_accuracy'] = max(1 - ((abs(current_test_iteration_counting_result.get('gabletop_count') - expected_counts['gabletop'])) / expected_counts['gabletop']), 0) * 100
                    current_test_iteration_counting_result['pouch_accuracy'] = max(1 - ((abs(current_test_iteration_counting_result.get('pouch_count') - expected_counts['pouch'])) / expected_counts['pouch']), 0) * 100
                    current_test_iteration_counting_result['frame_time_metrics'] = current_test_iteration_frame_time_metrics

                    other_iteration_results = list(filter(lambda e: e.get('file') == test_video_file_name, current_env_results))
                    other_iteration_results.append(current_test_iteration_counting_result)
                    for iteration_result in other_iteration_results:
                        iteration_result['iteration_diff'] = sum(list(map(lambda e: abs(e.get('count') - iteration_result.get('count')), other_iteration_results)))

                    current_env_results.append(current_test_iteration_counting_result)
                    current_test_video_file_name = test_video_file_name.split('.')[0]
                    with sv.VideoSink(f'{current_dest_folder}/{current_test_video_file_name}-{test_video_iteration+1}.mp4', sv.VideoInfo(height=int(current_env_height), width=int(current_env_width), fps=round(current_test_iteration_frame_time_metrics.get('avg_fps')), total_frames=len(current_test_iteration_frames))) as video_sink:
                        with tqdm.tqdm(current_test_iteration_frames, f'saving output frames to file for iteration #{test_video_iteration+1}/{ITERATIONS_PER_TEST} of {test_video_file_name} {test_video_index+1}/{num_of_video_files} for env {env} {env_index+1}/{num_of_dotenv_files}') as pbar:
                            for encoded_frame in current_test_iteration_frames:
                                base64_decoded = base64.b64decode(encoded_frame)
                                decoded_frame = jpeg.decode(base64_decoded)
                                video_sink.write_frame(decoded_frame)
                                pbar.update()

                    current_iteration_end = perf_counter()
                    iteration_result['time_s'] = current_iteration_end - current_iteration_start

                    current_env_overall_results = {
                        'env': env,
                        'avg_accuracy': sum(list(map(lambda e: e.get('accuracy'), current_env_results))) / len(current_env_results),
                        'avg_can_accuracy': sum(list(map(lambda e: e.get('can_accuracy'), current_env_results))) / len(current_env_results),
                        'avg_plastic_accuracy': sum(list(map(lambda e: e.get('plastic_accuracy'), current_env_results))) / len(current_env_results),
                        'avg_drinkbox_accuracy': sum(list(map(lambda e: e.get('drinkbox_accuracy'), current_env_results))) / len(current_env_results),
                        'avg_gabletop_accuracy': sum(list(map(lambda e: e.get('gabletop_accuracy'), current_env_results))) / len(current_env_results),
                        'avg_pouch_accuracy': sum(list(map(lambda e: e.get('pouch_accuracy'), current_env_results))) / len(current_env_results),
                        'avg_fps': sum(list(map(lambda e: e.get('frame_time_metrics').get('avg_fps'), current_env_results))) / len(current_env_results),
                        'avg_iteration_diff': sum(list(map(lambda e: e.get('iteration_diff'), current_env_results))) / len(current_env_results),
                        'time_s': current_iteration_end - current_env_start
                    }

                    with open(f'{current_dest_folder}/results.json', 'w') as f:
                        json.dump({**current_env_overall_results, 'results': current_env_results}, f, indent=4)

                    overall_results[len(overall_results) - 1] = current_env_overall_results

                    with open(f'{dest_folder}/overall_results.json', 'w') as f:
                        json.dump({ 'time_s': current_iteration_end - test_starting_time, 'overall_results': overall_results }, f, indent=4)

                    current_test_iteration_frame_time_metrics = {}
                    current_test_iteration_counting_result = {
                        'count': 0,
                        'can_count': 0,
                        'plastic_count': 0,
                        'drinkbox_count': 0,
                        'gabletop_count': 0,
                        'pouch_count': 0
                    }
                    current_test_iteration_frames = []

        print('Disconnecting socketio client...')
        client.disconnect()
        counter_app_process.terminate()
        print('waiting for counter app process to terminate')
        counter_app_process.wait()

if __name__ == '__main__':
    src_folder = sys.argv[1]
    dest_folder = sys.argv[2]
    env_folder = sys.argv[3]
    counter_app_tester(src_folder, dest_folder, env_folder)