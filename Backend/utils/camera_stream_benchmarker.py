from linuxpy.video.device import Device
from time import perf_counter_ns
import sys

def camera_stream_benchmarker(camera_id: int = 0):
    with Device.from_id(camera_id) as cam:
        avg_frame_time = 0
        end_of_last_frame = perf_counter_ns()
        for i, frame in enumerate(cam):
            start_of_current_frame = perf_counter_ns()
            frame_time = (start_of_current_frame - end_of_last_frame) / 1_000_000
            avg_frame_time = (avg_frame_time * i + frame_time) / (i + 1)
            print(f"avg_frame_time: {avg_frame_time:0.2f} ms, avg_fps: {(1000 / avg_frame_time):0.2f}")
            end_of_last_frame = perf_counter_ns()


if __name__ == '__main__':
    camera_id = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0
    camera_stream_benchmarker(camera_id)
