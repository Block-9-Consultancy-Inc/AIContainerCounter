import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib, GObject
import os
import numpy as np
import signal
from time import perf_counter
import cv2
from collections.abc import Callable
from threading import Thread
from get_frame_index_from_buffer import load_get_frame_index_from_buffer

# -----------------------------------------------------------------------------------------------
# User-defined class to be used in the callback function
# -----------------------------------------------------------------------------------------------
# A sample class to be used in the callback function
# This example allows to:
# 1. Count the number of frames
# 2. Setup a multiprocessing queue to pass the frame to the main thread
# Additional variables and functions can be added to this class as needed

class AppCallback:
    def __init__(self):
        self.running = True
prev_time = perf_counter()
num_of_frames = 0
avg_frame_time = 0

get_frame_index_from_buffer = load_get_frame_index_from_buffer()

def dummy_app_callback(pad, info, user_data):
    global avg_frame_time, prev_time, num_of_frames
    """
    A minimal dummy callback function that returns immediately.

    Args:
        pad: The GStreamer pad
        info: The probe info
        user_data: User-defined data passed to the callback

    Returns:
        Gst.PadProbeReturn.OK
    """
    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK
    
    frame_index = get_frame_index_from_buffer(buffer)

    print(f'FRAME INDEX: {frame_index}')

    format, width, height = get_caps_from_pad(pad)
    
    # print(f'{format=}, {width=}, {height=}')
    frame = get_numpy_from_buffer(buffer, format, width, height)
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    # cv2.imwrite('test.jpg', frame)
    current_time = perf_counter()

    avg_frame_time = (avg_frame_time * num_of_frames + (current_time - prev_time)) / (num_of_frames + 1)
    num_of_frames += 1
    prev_time = current_time

    # print(f'avg fps: {(1 / avg_frame_time):.2f}')

    return Gst.PadProbeReturn.OK

# -----------------------------------------------------------------------------------------------
# Common functions
# -----------------------------------------------------------------------------------------------

def get_caps_from_pad(pad: Gst.Pad):
    caps = pad.get_current_caps()
    if caps:
        # We can now extract information from the caps
        structure = caps.get_structure(0)
        if structure:
            # Extracting some common properties
            format = structure.get_value('format')
            width = structure.get_value('width')
            height = structure.get_value('height')
            return format, width, height
    else:
        return None, None, None

#---------------------------------------------------------
# Pipeline helper functions
#---------------------------------------------------------

def QUEUE(name, max_size_buffers=6, max_size_bytes=0, max_size_time=0, leaky='no'):
    """
    Creates a GStreamer queue element string with the specified parameters.

    Args:
        name (str): The name of the queue element.
        max_size_buffers (int, optional): The maximum number of buffers that the queue can hold. Defaults to 3.
        max_size_bytes (int, optional): The maximum size in bytes that the queue can hold. Defaults to 0 (unlimited).
        max_size_time (int, optional): The maximum size in time that the queue can hold. Defaults to 0 (unlimited).
        leaky (str, optional): The leaky type of the queue. Can be 'no', 'upstream', or 'downstream'. Defaults to 'no'.

    Returns:
        str: A string representing the GStreamer queue element with the specified parameters.
    """
    q_string = f'queue name={name} leaky={leaky} max-size-buffers={max_size_buffers} max-size-bytes={max_size_bytes} max-size-time={max_size_time} '
    return q_string

def SOURCE_PIPELINE(video_format='RGB', fps=30, name='source'):
    """
    Creates a GStreamer pipeline string for the video source.

    Args:
        video_source (str): The path or device name of the video source.
        video_format (str, optional): The video format. Defaults to 'RGB'.
        video_width (int, optional): The width of the video. Defaults to 640.
        video_height (int, optional): The height of the video. Defaults to 640.
        name (str, optional): The prefix name for the pipeline elements. Defaults to 'source'.

    Returns:
        str: A string representing the GStreamer pipeline for the video source.
    """
    source_pipeline = (
        f'{QUEUE(name=f"video_rate_q")} ! videorate max-rate={fps} ! '
        f'{QUEUE(name=f"{name}_convert_q")} ! '
        f'videoconvert n-threads=3 name={name}_convert qos=false ! '
        f'video/x-raw, format={video_format} ! '
    )

    return source_pipeline

def USER_CALLBACK_PIPELINE(name='identity_callback'):
    """
    Creates a GStreamer pipeline string for the user callback element.

    Args:
        name (str, optional): The prefix name for the pipeline elements. Defaults to 'identity_callback'.

    Returns:
        str: A string representing the GStreamer pipeline for the user callback element.
    """
    # Construct the user callback pipeline string
    user_callback_pipeline = (
        f'{QUEUE(name=f"frameindexer_q")} ! frameindexer name=frameindexer ! '
        f'{QUEUE(name=f"{name}_q")} ! '
        f'identity name={name} '
    )

    return user_callback_pipeline

SUPPORTED_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts', '.mpg', '.mpeg')

# -----------------------------------------------------------------------------------------------
# GStreamerApp class
# -----------------------------------------------------------------------------------------------
class GStreamerApp:
    def __init__(
            self,
            on_state_changed: Callable,
            on_stopped: Callable,
            first_file_name: str,
            video_dir: str,
            fps: int,
            user_data,
            socket_path = 'test.socket'
        ):
        # Set up signal handler for SIGINT (Ctrl-C)
        Gst.init(None)
        signal.signal(signal.SIGINT, self.shutdown)
        self.video_files = []
        self.current_video_index = -1
        self.frameindexer = None
        self.first_file_path = first_file_name
        self.fps = fps
        self.video_dir = video_dir
        self.current_path = os.path.dirname(os.path.abspath(__file__))
        self.user_data = user_data
        self.pipeline = None
        self.data_collection_pipeline = None
        self.app_callback = None
        self.data_collection_callback = None
        self.new_location_callback = None
        self.collect_raw_frames = True
        self.socket_path = socket_path
        self.status = 'stopped'
        self.on_state_changed = on_state_changed
        self.on_state_changed(self.status)
        self.on_stopped = on_stopped
        self.first_stream_started = False
        self.scan_video_directory()

    def scan_video_directory(self):
        print(f"Scanning for videos in: {os.path.abspath(self.video_dir)}")
        if not os.path.isdir(self.video_dir):
            print(f"Error: Directory '{self.video_dir}' not found.")
            return

        for item in sorted(os.listdir(self.video_dir)): # Sort for predictable order
            if item.lower().endswith(SUPPORTED_EXTENSIONS):
                self.video_files.append(os.path.join(os.path.abspath(self.video_dir), item))
        print(f"Found videos: {self.video_files}")


    def on_fps_measurement(self, sink, fps, droprate, avgfps):
        print(f"FPS: {fps:.2f}, Droprate: {droprate:.2f}, Avg FPS: {avgfps:.2f}")
        return True

    def create_pipeline(self):
        # Initialize GStreamer
        pipeline_string = self.get_pipeline_string()
        try:
            self.pipeline = Gst.ElementFactory.make("playbin3", "player")

            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self.bus_call)

            self.videosink_bin = Gst.parse_bin_from_description(pipeline_string, True)
            self.frameindexer = self.videosink_bin.get_by_name("frameindexer")

            identity = self.videosink_bin.get_by_name("identity_callback")
            if identity is None:
                print("Warning: identity_callback element not found, add <identity name=identity_callback> in your pipeline where you want the callback to be called.")
            else:
                identity_pad = identity.get_static_pad("src")
                identity_pad.add_probe(Gst.PadProbeType.BUFFER, self.app_callback, self.user_data)

            self.pipeline.set_property("video-sink", self.videosink_bin)
            self.pipeline.set_property("flags", 0x5)

            self.pipeline.connect("about-to-finish", self.on_about_to_finish)

            # Disable QoS to prevent frame drops
            disable_qos(self.pipeline)
            disable_qos(self.videosink_bin)
        except Exception as e:
            print(f'error with main pipeline: {e}')
            print(pipeline_string)
            sys.exit(1)

        if self.collect_raw_frames:
            data_collection_pipeline_string = self.get_raw_feed_collection_pipeline_string(self.first_file_path)
            try:
                self.data_collection_pipeline = Gst.parse_launch(data_collection_pipeline_string)
                splitmuxsink = self.data_collection_pipeline.get_by_name('splitmuxsink')
                splitmuxsink.connect('format-location', self.new_location_callback, self.user_data)
                disable_qos(self.data_collection_pipeline)
            except Exception as e:
                print(f'error with data collection pipeline: {e}')
                print(data_collection_pipeline_string)
                sys.exit(1)

    def on_about_to_finish(self, player):
        print("\n--- about-to-finish: Current video ending ---")
        self.play_next_video()

    def play_next_video(self):
        if not self.video_files:
            print("No videos in playlist to play.")
            return

        self.current_video_index = (self.current_video_index + 1) % len(self.video_files)
        next_uri = GLib.filename_to_uri(self.video_files[self.current_video_index], None)

        print(f"Playing next: {self.video_files[self.current_video_index]} (URI: {next_uri})")
        self.pipeline.set_property("uri", next_uri)
        # Playbin should automatically go to PLAYING. If it was in PLAYING, setting URI re-triggers.
        # If it reached EOS and went to PAUSED/READY, explicitly set to PLAYING.
        self.pipeline.set_state(Gst.State.PLAYING)

    def bus_call(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("End-of-stream")
            self.on_eos()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}")
            self.shutdown()
        # QOS
        elif t == Gst.MessageType.QOS:
            # Handle QoS message here
            # qos_element = message.src.get_name()
            # print(f"QoS message received from {qos_element}")
            pass
        elif t == Gst.MessageType.STREAM_START:
            print(f'STREAM START MESSAGE RECEIVED')
            self.frameindexer.emit("reset-frame-index")
            if not self.first_stream_started and self.collect_raw_frames:
                print('STARTING RAW FRAME COLLECTION PIPELINE')
                self.first_stream_started = True
                self.data_collection_pipeline.set_state(Gst.State.PLAYING)

        return True


    def on_eos(self):
        # if self.source_type == "file":
        #      # Seek to the start (position 0) in nanoseconds
        #     success = self.pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, 0)
        #     if success:
        #         print("Video rewound successfully. Restarting playback...")
        #     else:
        #         print("Error rewinding the video.")
        # else:
        self.shutdown()


    def shutdown(self, signum=None, frame=None, error = None, debug = None, on_request=False):
        if signum is not None:
            print(f'got signum {signum}')
        if not on_request:
            print("Shutting down... Hit Ctrl-C again to force quit.")
            signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.first_stream_started = False
        self.on_stopped()
        GLib.usleep(500000)  # 0.1 second delay
        self.pipeline.set_state(Gst.State.PAUSED)
        if self.collect_raw_frames:
            self.data_collection_pipeline.set_state(Gst.State.PAUSED)
        GLib.usleep(100000)  # 0.1 second delay

        self.pipeline.set_state(Gst.State.READY)
        if self.collect_raw_frames:
            self.data_collection_pipeline.set_state(Gst.State.READY)
        GLib.usleep(100000)  # 0.1 second delay

        self.pipeline.set_state(Gst.State.NULL)
        if self.collect_raw_frames:
            self.data_collection_pipeline.set_state(Gst.State.NULL)
        self.status = 'stopped'
        self.on_state_changed(self.status, error=error, debug=debug)
        print('Pipeline now stopped fully')
        GLib.usleep(100000)  # 0.1 second delay
        if self.collect_raw_frames and on_request:
            print(f'ON REQUEST: {on_request}')
            self.create_pipeline()


    def get_pipeline_string(self):
        source_pipeline = SOURCE_PIPELINE(fps=self.fps)
        user_callback_pipeline = USER_CALLBACK_PIPELINE()
        display_pipeline = 'fakesink' if not self.collect_raw_frames else f'{QUEUE(name=f"valve_q")} ! valve name=valve drop=false ! {QUEUE(name=f"shmsink_q")} ! unixfdsink socket-path={self.socket_path} wait-for-connection=false'
        pipeline_string = (
            f'{source_pipeline} '
            f'{user_callback_pipeline} ! '
            f'{display_pipeline}'
        )

        print(f'main pipeline: {pipeline_string}')
        return pipeline_string
    
    def get_raw_feed_collection_pipeline_string(self, first_file_path):
        pipeline_string = (
            f'unixfdsrc socket-path={self.socket_path} ! '
            f'{QUEUE(name=f"jpegenc_q")} ! '
            f'jpegenc ! '
            f'{QUEUE(name=f"splitmuxsink_q")} ! '
            f'splitmuxsink name=splitmuxsink async-finalize=true muxer-factory=avimux location={first_file_path}'
        )

        print(f'raw feed collection pipeline: {pipeline_string}')
        return pipeline_string

    def dump_dot_file(self):
        print("Dumping dot file...")
        Gst.debug_bin_to_dot_file(self.pipeline, Gst.DebugGraphDetails.ALL, "pipeline")
        return False
    
    def signal_new_file(self):
        if not self.collect_raw_frames:
            return
        splitmuxsink = self.data_collection_pipeline.get_by_name('splitmuxsink')
        splitmuxsink.emit('split-now')

    def run(self):
        if self.status != 'stopped':
            print(f'Current pipeline status is {self.status}, cannot run from scratch')
            return

        # Set pipeline to PLAYING state
        self.play_next_video()

        self.status = 'playing'
        self.on_state_changed(self.status)
        print('Pipeline now running')



    def stop(self):
        # TODO need to handle new batch when process stops
        if self.status == 'stopped':
            print(f'Current pipeline status is already {self.status}, cannot stop again')
            return
        self.shutdown(on_request=True)
    
    def pause(self):
        if self.status != 'playing':
            print(f'Current pipeline status is already {self.status}, cannot pause')
            return
        if self.collect_raw_frames:
            valve = self.pipeline.get_by_name('valve')
            valve.set_property('drop', True)
        self.status = 'paused'
        self.on_state_changed(self.status)
        print('Pipeline now paused')


    def play(self):
        if self.status =='stopped':
            print('Pipeline stopped, attempting to run')
            self.run_thread = Thread(target=self.run)
            self.run_thread.start()
            return

        if self.status != 'paused':
            print(f'Current pipeline status is {self.status}, cannot play')
            return
        
        self.pipeline.set_state(Gst.State.PLAYING)
        if self.collect_raw_frames:
            valve = self.pipeline.get_by_name('valve')
            valve.set_property('drop', False)
        self.status = 'playing'
        self.on_state_changed(self.status)
        print('Pipeline now playing')

# ---------------------------------------------------------
# Functions used to get numpy arrays from GStreamer buffers
# ---------------------------------------------------------

def handle_rgb(map_info, width, height):
    # The copy() method is used to create a copy of the numpy array. This is necessary because the original numpy array is created from buffer data, and it does not own the data it represents. Instead, it's just a view of the buffer's data.
    return np.ndarray(shape=(height, width, 3), dtype=np.uint8, buffer=map_info.data).copy()

def handle_nv12(map_info, width, height):
    y_plane_size = width * height
    uv_plane_size = width * height // 2
    y_plane = np.ndarray(shape=(height, width), dtype=np.uint8, buffer=map_info.data[:y_plane_size]).copy()
    uv_plane = np.ndarray(shape=(height//2, width//2, 2), dtype=np.uint8, buffer=map_info.data[y_plane_size:]).copy()
    return y_plane, uv_plane

def handle_yuyv(map_info, width, height):
    return np.ndarray(shape=(height, width, 2), dtype=np.uint8, buffer=map_info.data).copy()

FORMAT_HANDLERS = {
    'RGB': handle_rgb,
    'NV12': handle_nv12,
    'YUYV': handle_yuyv,
}

def get_numpy_from_buffer(buffer, format, width, height):
    """
    Converts a GstBuffer to a numpy array based on provided format, width, and height.

    Args:
        buffer (GstBuffer): The GStreamer Buffer to convert.
        format (str): The video format ('RGB', 'NV12', 'YUYV', etc.).
        width (int): The width of the video frame.
        height (int): The height of the video frame.

    Returns:
        np.ndarray: A numpy array representing the buffer's data, or a tuple of arrays for certain formats.
    """
    # Map the buffer to access data
    success, map_info = buffer.map(Gst.MapFlags.READ)
    if not success:
        raise ValueError("Buffer mapping failed")

    try:
        # Handle different formats based on the provided format parameter
        handler = FORMAT_HANDLERS.get(format)
        if handler is None:
            raise ValueError(f"Unsupported format: {format}")
        return handler(map_info, width, height)
    finally:
        buffer.unmap(map_info)

def get_caps_from_pad(pad: Gst.Pad):
    caps = pad.get_current_caps()
    if caps:
        # We can now extract information from the caps
        structure = caps.get_structure(0)
        if structure:
            # Extracting some common properties
            format = structure.get_value('format')
            width = structure.get_value('width')
            height = structure.get_value('height')
            return format, width, height
    else:
        return None, None, None

# ---------------------------------------------------------
# Useful functions for working with GStreamer
# ---------------------------------------------------------

def disable_qos(pipeline):
    """
    Iterate through all elements in the given GStreamer pipeline and set the qos property to False
    where applicable.
    When the 'qos' property is set to True, the element will measure the time it takes to process each buffer and will drop frames if latency is too high.
    We are running on long pipelines, so we want to disable this feature to avoid dropping frames.
    :param pipeline: A GStreamer pipeline object
    """
    # Ensure the pipeline is a Gst.Pipeline instance
    # if not isinstance(pipeline, Gst.Pipeline):
    #     print("The provided object is not a GStreamer Pipeline")
    #     return

    # Iterate through all elements in the pipeline
    it = pipeline.iterate_elements()
    while True:
        result, element = it.next()
        if result != Gst.IteratorResult.OK:
            break

        # Check if the element has the 'qos' property
        if 'qos' in GObject.list_properties(element):
            # Set the 'qos' property to False
            element.set_property('qos', False)
            print(f"Set qos to False for {element.get_name()}")


if __name__ == '__main__':
    if os.path.exists('test.socket'):
        os.remove('test.socket')
    def on_state_changed(status, error=None, debug=None):
        print(f'state changed: {status}')
    def on_stopped():
        print('on stopped called')

    def new_location_callback(splitmux, fragment_id, user_data):
        return f'test.avi'
    
    gstreamer_app = GStreamerApp(
        on_state_changed=on_state_changed,
        on_stopped=on_stopped,
        first_file_name='test.avi',
        video_dir='videos',
        fps=30,
        user_data=AppCallback()
        
    )
    gstreamer_app.app_callback = dummy_app_callback
    gstreamer_app.new_location_callback = new_location_callback
    gstreamer_app.create_pipeline()
    gstreamer_app.run()
    GLib.MainLoop().run()