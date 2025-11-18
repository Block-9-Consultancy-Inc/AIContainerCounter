from linuxpy.video.device import Device
from time import perf_counter_ns

with Device.from_id(0) as cam:
    avg_frame_time = 0
    end_of_last_frame = perf_counter_ns()
    for i, frame in enumerate(cam):
        start_of_current_frame = perf_counter_ns()
        frame_time = (start_of_current_frame - end_of_last_frame) / 1_000_000
        avg_frame_time = (avg_frame_time * i + frame_time) / (i + 1)
        print(f"avg_frame_time: {avg_frame_time:0.2f} ms, avg_fps: {(1000 / avg_frame_time):0.2f}")
        end_of_last_frame = perf_counter_ns()
