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
import signal
import cv2
import multiprocessing

gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
from gi.repository import Gst, GstPbutils

Gst.init(sys.argv[0:1])

stop_now = False

def handler_stop_signals(signum, frame):
    global stop_now
    stop_now = True

signal.signal(signal.SIGINT, handler_stop_signals)
signal.signal(signal.SIGTERM, handler_stop_signals)


def get_file_duration(file: Path) -> float:
    discoverer = GstPbutils.Discoverer()
    asset_info = discoverer.discover_uri(str(file.as_uri()))
    duration_in_seconds = asset_info.get_duration() / 1_000_000_000
    
    return duration_in_seconds

def start_video_stream_to_v4l2loopback_dummy_device(test_video_file_path: str, loop = False, camera_id = 0):
    if loop:
        process = Popen(['ffmpeg', '-stream_loop', '-1', '-re', '-i', test_video_file_path, '-c:v', 'copy', '-f', 'v4l2', f'/dev/video{camera_id}'], stdout=DEVNULL, stderr=DEVNULL)
    else:
        process = Popen(['ffmpeg', '-re', '-i', test_video_file_path, '-c:v', 'copy', '-f', 'v4l2', f'/dev/video{camera_id}'], stdout=DEVNULL, stderr=DEVNULL)
    return process


def start_detection_process(dotenv_path: str):
    process = Popen(['python', 'counter_app.py', dotenv_path, 'test'], stdout=DEVNULL, stderr=DEVNULL)
    return process

def video_writer(event_queue: multiprocessing.Queue):
    jpeg = TurboJPEG()
    writers = {}  # Dictionary to hold VideoWriter objects

    while True:
        event = event_queue.get()

        if event is None:  # Use None to signal shutdown
            break

        event_type = event["type"]
        test_case_id = event["test_case_id"]

        if event_type == "test_case_start":
            # Create output directory if not exists
            output_path = event.get('dest_file_path')

            # Initialize VideoWriter
            frame_size = tuple(event["frame_size"])  # (width, height)
            fps = event.get("fps", 20)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

            writers[test_case_id] = cv2.VideoWriter(output_path, fourcc, fps, frame_size)

        elif event_type == "test_case_frame":
            encoded_frame = event["encoded_frame"]
            if test_case_id in writers:
                base64_decoded = base64.b64decode(encoded_frame)
                decoded_frame = jpeg.decode(base64_decoded)
                writers[test_case_id].write(decoded_frame)

        elif event_type == "test_case_end":
            if test_case_id in writers:
                writer_to_release = writers[test_case_id]
                del writers[test_case_id]
                writer_to_release.release()

def sleep_with_progress(duration: float, description: str):
    remaining_duration = duration
    with tqdm.tqdm(total=duration, desc=description) as pbar:
        while remaining_duration > 0:
            if stop_now:
                return
            time_to_sleep = 1 if remaining_duration >= 1 else remaining_duration
            sleep(time_to_sleep)
            remaining_duration -= time_to_sleep
            pbar.update(time_to_sleep)

def calculate_accuracy(expected: int, actual: int) -> float:
    if expected == 0:
        expected += 1
        actual += 1
    return max(1 - ((abs(actual - expected)) / expected), 0) * 100

def counter_app_tester(src_folder: str, dest_folder: str, env_folder: str, camera_id = 0):
    test_starting_time = perf_counter()
    client = socketio.Client()
   # Create the event queue
    frame_writer_queue = multiprocessing.Queue()
    # Start the video writer process
    video_writer_process = multiprocessing.Process(target=video_writer, args=[frame_writer_queue])
    video_writer_process.start()

    current_test_iteration_frame_time_metrics = {}
    current_test_iteration_counting_result = {
        'count': 0,
        'can_count': 0,
        'plastic_count': 0,
        'drinkbox_count': 0,
        'gabletop_count': 0,
        'pouch_count': 0
    }
    current_test_case = None
    client_initializing = True
    batch_done = False
    @client.on('detection_event')
    def on_detection_event(message):
        # print(f'detection event with count: {message.get('count')}')
        if message.get('current_test_case') != current_test_case:
            return
        current_test_iteration_counting_result['count'] = max(message.get('count'), current_test_iteration_counting_result['count'])
        current_test_iteration_counting_result['can_count'] = max(message.get('can_count'), current_test_iteration_counting_result['can_count'])
        current_test_iteration_counting_result['plastic_count'] = max(message.get('plastic_count'), current_test_iteration_counting_result['plastic_count'])
        current_test_iteration_counting_result['drinkbox_count'] = max(message.get('drinkbox_count'), current_test_iteration_counting_result['drinkbox_count'])
        current_test_iteration_counting_result['gabletop_count'] = max(message.get('gabletop_count'), current_test_iteration_counting_result['gabletop_count'])
        current_test_iteration_counting_result['pouch_count'] = max(message.get('pouch_count'), current_test_iteration_counting_result['pouch_count'])
        frame_writer_queue.put({
            'type': 'test_case_frame',
            'test_case_id': current_test_case,
            'encoded_frame': message.get('encoded_frame')
        })

    @client.on('frame_time')
    def on_frame_time(message):
        if message.get('current_test_case') != current_test_case:
            return
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

    overall_env_results = []
    overall_batch_results = {}

    for env_index, env in enumerate(dotenv_files):
        current_env_start = perf_counter()
        overall_batch_results[env] = []
        current_env_overall_results = {
            'env': env,
            'overall_accuracy': 0,
            'overall_fps': 0,
            'batch_results': []
        }
        overall_env_results.append(current_env_overall_results)
        current_env_results = []
        current_env_path = f'{env_folder}/{env}'
        current_env_values = dotenv_values(current_env_path)
        current_env_height, current_env_width, current_env_fps = current_env_values.get('HEIGHT', '1080'), current_env_values.get('WIDTH', '1920'), int(current_env_values.get('CAMERA_FPS', 30))
        current_env_name = env.split('.')[0]

        print('initializing counter app with empty frames')
        intro_file = f'{src_folder}/intro.avi'
        video_duration = get_file_duration(Path(intro_file))
        video_playback_process = start_video_stream_to_v4l2loopback_dummy_device(intro_file, loop=True, camera_id=camera_id)
        waiting_thread = Thread(target=sleep_with_progress, args=[video_duration + 5, f'Waiting for intro video to finish to initialize counter app'])
        counter_app_process = start_detection_process(current_env_path)
        waiting_thread.start()
        client.connect(url='http://0.0.0.0:5000', transports=['polling'], namespaces=['/'], retry=True)
        waiting_thread.join()
        video_playback_process.terminate()
        video_playback_process.wait()
        client_initializing = False

        if stop_now:
            counter_app_process.terminate()
            print('waiting for counter app process to terminate')
            counter_app_process.wait()
            sys.exit(0)

        current_env_dest_folder = f'{dest_folder}/{current_env_name}'
        batches = os.listdir(src_folder)
        num_of_batches = len(batches)
        for batch_index, batch in enumerate(reversed(batches)):
            if batch == 'intro.avi':
                continue
            current_batch_start = perf_counter()
            current_batch_overall_results = {
                'batch': batch,
                'overall_accuracy': 0,
                'overall_fps': 0,
                'results': [],
            }
            overall_batch_results[env].append(current_batch_overall_results)
            current_batch_results = []
            
            with open(f'{src_folder}/{batch}/breakdown.json') as f:
                expected_counts = json.load(f)
            video_files = os.listdir(f'{src_folder}/{batch}')
            video_files.sort()
            num_of_video_files = len(video_files)
            current_batch_dest_folder = f'{current_env_dest_folder}/{batch}'
            os.makedirs(current_batch_dest_folder, exist_ok=True)
            for test_video_index, test_video_file_name in enumerate(video_files):
                if test_video_file_name.endswith('.json'):
                    continue
                file = f'{src_folder}/{batch}/{test_video_file_name}'
                print(f'file: {file}')
                if os.path.isfile(f'{current_batch_dest_folder}/results.json'):
                    with open(f'{current_batch_dest_folder}/results.json') as f:
                        results_json = json.load(f)
                    existing_result = list(filter(lambda e: e.get('file') == test_video_file_name,  results_json.get('results', [])))
                    if len(existing_result) > 0:
                        print(f'SKIPPING: {batch} {test_video_file_name}')
                        continue
                    else:
                        print(f'No test found in results json for {batch} {test_video_file_name}')
                else:
                    print(f'No results json exists for {batch} {test_video_file_name}')

                current_test_case = f'{current_env_name}/{batch}/{test_video_file_name}'
                client.emit('new-test-case', current_test_case)

                current_test_video_file_name = test_video_file_name.split('.')[0]
                frame_writer_queue.put({
                    'type': 'test_case_start',
                    'test_case_id': current_test_case,
                    'dest_file_path': f'{current_batch_dest_folder}/{current_test_video_file_name}.mp4',
                    'fps': float(current_env_fps),
                    'frame_size': (int(current_env_width), int(current_env_height))
                })

                video_duration = get_file_duration(Path(file))
                video_playback_process = start_video_stream_to_v4l2loopback_dummy_device(file, camera_id=camera_id)
                waiting_thread = Thread(target=sleep_with_progress, args=[video_duration + 2, f'Running test {test_video_file_name} {test_video_index+1}/{num_of_video_files} for batch {batch} {batch_index + 1}/{num_of_batches} for env {env} {env_index+1}/{num_of_dotenv_files}'])
                waiting_thread.start()
                waiting_thread.join()

                if stop_now:
                    video_playback_process.terminate()
                    video_playback_process.wait()
                    print('waiting for video playback process to terminate')
                    counter_app_process.terminate()
                    print('waiting for counter app process to terminate')
                    counter_app_process.wait()
                    sys.exit(0)
                
                video_playback_process = start_video_stream_to_v4l2loopback_dummy_device(intro_file, loop=True, camera_id=camera_id)
                client.emit('reset-count', 'reset-count')
                while not batch_done:
                    print('batch not done yet')
                    if stop_now:
                        video_playback_process.terminate()
                        video_playback_process.wait()
                        print('waiting for video playback process to terminate')
                        counter_app_process.terminate()
                        print('waiting for counter app process to terminate')
                        counter_app_process.wait()
                        sys.exit(0)
                    sleep(0.25)
                
                batch_done = False
                waiting_thread = Thread(target=sleep_with_progress, args=[3, f'Waiting 3 seconds for all socket io events to be transmitted'])
                waiting_thread.start()
                waiting_thread.join()

                video_playback_process.terminate()
                video_playback_process.wait()

                print(current_test_iteration_counting_result)
                current_test_iteration_counting_result['file'] = test_video_file_name
                current_test_iteration_counting_result['accuracy'] = calculate_accuracy(expected_counts['total'], current_test_iteration_counting_result.get('count'))
                current_test_iteration_counting_result['can_accuracy'] = calculate_accuracy(expected_counts['can'], current_test_iteration_counting_result.get('can_count'))
                current_test_iteration_counting_result['plastic_accuracy'] = calculate_accuracy(expected_counts['plastic'], current_test_iteration_counting_result.get('plastic_count'))
                current_test_iteration_counting_result['drinkbox_accuracy'] = calculate_accuracy(expected_counts['drinkbox'], current_test_iteration_counting_result.get('drinkbox_count'))
                current_test_iteration_counting_result['gabletop_accuracy'] = calculate_accuracy(expected_counts['gabletop'], current_test_iteration_counting_result.get('gabletop_count'))
                current_test_iteration_counting_result['pouch_accuracy'] = calculate_accuracy(expected_counts['pouch'], current_test_iteration_counting_result.get('pouch_count'))
                current_test_iteration_counting_result['frame_time_metrics'] = current_test_iteration_frame_time_metrics


                current_batch_results.append(current_test_iteration_counting_result)
                current_env_results.append(current_test_iteration_counting_result)

                current_iteration_end = perf_counter()

                current_batch_overall_results = {
                    'batch': batch,
                    'avg_accuracy': sum(list(map(lambda e: e.get('accuracy'), current_batch_results))) / len(current_batch_results),
                    'avg_can_accuracy': sum(list(map(lambda e: e.get('can_accuracy'), current_batch_results))) / len(current_batch_results),
                    'avg_plastic_accuracy': sum(list(map(lambda e: e.get('plastic_accuracy'), current_batch_results))) / len(current_batch_results),
                    'avg_drinkbox_accuracy': sum(list(map(lambda e: e.get('drinkbox_accuracy'), current_batch_results))) / len(current_batch_results),
                    'avg_gabletop_accuracy': sum(list(map(lambda e: e.get('gabletop_accuracy'), current_batch_results))) / len(current_batch_results),
                    'avg_pouch_accuracy': sum(list(map(lambda e: e.get('pouch_accuracy'), current_batch_results))) / len(current_batch_results),
                    'avg_fps': sum(list(map(lambda e: e.get('frame_time_metrics').get('avg_frame_latencies').get('fps'), current_batch_results))) / len(current_batch_results),
                    'time_s': current_iteration_end - current_batch_start
                }

                with open(f'{current_batch_dest_folder}/results.json', 'w') as f:
                    json.dump({**current_batch_overall_results, 'results': current_batch_results}, f, indent=4)

                current_env_overall_results = {
                    'env': env,
                    'avg_accuracy': sum(list(map(lambda e: e.get('accuracy'), current_env_results))) / len(current_env_results),
                    'avg_can_accuracy': sum(list(map(lambda e: e.get('can_accuracy'), current_env_results))) / len(current_env_results),
                    'avg_plastic_accuracy': sum(list(map(lambda e: e.get('plastic_accuracy'), current_env_results))) / len(current_env_results),
                    'avg_drinkbox_accuracy': sum(list(map(lambda e: e.get('drinkbox_accuracy'), current_env_results))) / len(current_env_results),
                    'avg_gabletop_accuracy': sum(list(map(lambda e: e.get('gabletop_accuracy'), current_env_results))) / len(current_env_results),
                    'avg_pouch_accuracy': sum(list(map(lambda e: e.get('pouch_accuracy'), current_env_results))) / len(current_env_results),
                    'avg_fps': sum(list(map(lambda e: e.get('frame_time_metrics').get('avg_frame_latencies').get('fps'), current_env_results))) / len(current_env_results),
                    'time_s': current_iteration_end - current_env_start
                }

                with open(f'{current_env_dest_folder}/results.json', 'w') as f:
                    json.dump({**current_env_overall_results, 'results': current_env_results}, f, indent=4)

                overall_batch_results[env][len(overall_batch_results[env]) - 1] = current_batch_overall_results

                overall_env_results[len(overall_env_results) - 1] = current_env_overall_results

                with open(f'{dest_folder}/overall_results.json', 'w') as f:
                    json.dump({ 'time_s': current_iteration_end - test_starting_time, 'overall_env_results': overall_env_results, 'overall_batch_results': overall_batch_results }, f, indent=4)

                current_test_iteration_frame_time_metrics = {}
                current_test_iteration_counting_result = {
                    'count': 0,
                    'can_count': 0,
                    'plastic_count': 0,
                    'drinkbox_count': 0,
                    'gabletop_count': 0,
                    'pouch_count': 0
                }

                frame_writer_queue.put({
                    'type': 'test_case_end',
                    'test_case_id': current_test_case,
                })

                if stop_now:
                    counter_app_process.terminate()
                    print('waiting for counter app process to terminate')
                    counter_app_process.wait()
                    sys.exit(0)

        print('Disconnecting socketio client...')
        client.disconnect()
        counter_app_process.terminate()
        print('waiting for counter app process to terminate')
        counter_app_process.wait()
        frame_writer_queue.put(None)

if __name__ == '__main__':
    src_folder = sys.argv[1]
    dest_folder = sys.argv[2]
    env_folder = sys.argv[3]
    camera_id = os.environ.get('CAMERA_ID', 0)
    counter_app_tester(src_folder, dest_folder, env_folder, camera_id=camera_id)