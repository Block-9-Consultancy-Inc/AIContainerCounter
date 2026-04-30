import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib, GObject
import os
import numpy as np
import signal
from time import perf_counter
import cv2

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
    
    frame = get_numpy_from_buffer(buffer, 'RGB', 1920, 1080)
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    cv2.imwrite('test.jpg', frame)
    current_time = perf_counter()

    avg_frame_time = (avg_frame_time * num_of_frames + (current_time - prev_time)) / (num_of_frames + 1)
    num_of_frames += 1
    prev_time = current_time

    print(f'avg fps: {(1 / avg_frame_time):.2f}')

    return Gst.PadProbeReturn.OK

def dummy_data_collection_callback(pad, info, user_data):
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

def QUEUE(name, max_size_buffers=3, max_size_bytes=0, max_size_time=0, leaky='no'):
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

def SOURCE_PIPELINE(video_source, video_format='RGB', video_width=1920, video_height=1080, fps=30, name='source'):
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
    source_element = (
        f'v4l2src device={video_source} name={name} ! image/jpeg, width={video_width}, height={video_height}, framerate={fps}/1 ! tee name=t '
        f't. ! {QUEUE(name=f"display_tee_q")} ! jpegdec ! '
    )
    source_pipeline = (
        f'{source_element} '
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
        f'{QUEUE(name=f"{name}_q")} ! '
        f'identity name={name} '
    )

    return user_callback_pipeline
# -----------------------------------------------------------------------------------------------
# GStreamerApp class
# -----------------------------------------------------------------------------------------------
class GStreamerApp:
    def __init__(self, first_file_name: str, video_source: str, width: int, height: int, fps: int, user_data, socket_path = 'test.socket'):
        # Set up signal handler for SIGINT (Ctrl-C)
        signal.signal(signal.SIGINT, self.shutdown)
        self.first_file_path = first_file_name
        self.width = width
        self.height = height
        self.fps = fps
        self.video_source = video_source
        self.current_path = os.path.dirname(os.path.abspath(__file__))
        self.user_data = user_data
        self.pipeline = None
        self.data_collection_pipeline = None
        self.app_callback = None
        self.data_collection_callback = None
        self.new_location_callback = None
        self.collect_raw_frames = True
        self.socket_path = socket_path


    def on_fps_measurement(self, sink, fps, droprate, avgfps):
        print(f"FPS: {fps:.2f}, Droprate: {droprate:.2f}, Avg FPS: {avgfps:.2f}")
        return True

    def create_pipeline(self):
        # Initialize GStreamer
        Gst.init(None)

        pipeline_string = self.get_pipeline_string()
        try:
            self.pipeline = Gst.parse_launch(pipeline_string)
        except Exception as e:
            print(f'error with main pipeline: {e}')
            print(pipeline_string)
            sys.exit(1)

        if self.collect_raw_frames:
            data_collection_pipeline_string = self.get_raw_feed_collection_pipeline_string()
            try:
                self.data_collection_pipeline = Gst.parse_launch(data_collection_pipeline_string)
            except Exception as e:
                print(f'error with data collection pipeline: {e}')
                print(data_collection_pipeline_string)
                sys.exit(1)


    def bus_call(self, bus, message, loop):
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


    def shutdown(self, signum=None, frame=None):
        print("Shutting down... Hit Ctrl-C again to force quit.")
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.pipeline.set_state(Gst.State.PAUSED)
        GLib.usleep(100000)  # 0.1 second delay

        self.pipeline.set_state(Gst.State.READY)
        GLib.usleep(100000)  # 0.1 second delay

        self.pipeline.set_state(Gst.State.NULL)


    def get_pipeline_string(self):
        source_pipeline = SOURCE_PIPELINE(self.video_source, video_width=self.width, video_height=self.height, fps=self.fps)
        user_callback_pipeline = USER_CALLBACK_PIPELINE()
        display_pipeline = 'fakesink'
        pipeline_string = (
            f'{source_pipeline} '
            f'{user_callback_pipeline} ! '
            f'{display_pipeline}'
        )
        if self.collect_raw_frames:
            pipeline_string += f' t. ! {QUEUE(name=f"shmsink_q")} ! shmsink socket-path={self.socket_path} wait-for-connection=false'

        print(f'main pipeline: {pipeline_string}')
        return pipeline_string
    
    def get_raw_feed_collection_pipeline_string(self):
        pipeline_string = (
            f'shmsrc do-timestamp=true socket-path={self.socket_path} ! '
            f'image/jpeg, width={self.width}, height={self.height}, framerate={self.fps}/1  ! '
            f'{QUEUE(name=f"data_collection_callback_q")} ! '
            'identity name=data_collection_callback ! '
            f'{QUEUE(name=f"splitmuxsink_q")} ! '
            f'splitmuxsink name=splitmuxsink async-finalize=true muxer-factory=avimux location={self.first_file_path}'
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
        # Add a watch for messages on the pipeline's bus
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.bus_call)


        # Connect pad probe to the identity element
        identity = self.pipeline.get_by_name("identity_callback")
        if identity is None:
            print("Warning: identity_callback element not found, add <identity name=identity_callback> in your pipeline where you want the callback to be called.")
        else:
            identity_pad = identity.get_static_pad("src")
            identity_pad.add_probe(Gst.PadProbeType.BUFFER, self.app_callback, self.user_data)

        # Disable QoS to prevent frame drops
        disable_qos(self.pipeline)

        # Set pipeline to PLAYING state
        self.pipeline.set_state(Gst.State.PLAYING)


                # Connect pad probe to the identity element
        if self.collect_raw_frames:
            splitmuxsink = self.data_collection_pipeline.get_by_name('splitmuxsink')
            splitmuxsink.connect('format-location', self.new_location_callback, self.user_data)
            identity = self.data_collection_pipeline.get_by_name("data_collection_callback")
            if identity is None:
                print("Warning: data_collection_callback element not found, add <identity name=data_collection_callback> in your pipeline where you want the callback to be called.")
            else:
                identity_pad = identity.get_static_pad("src")
                identity_pad.add_probe(Gst.PadProbeType.BUFFER, self.data_collection_callback, self.user_data)

            disable_qos(self.data_collection_pipeline)

            GLib.usleep(2000000)  # 2 second delay
            self.data_collection_pipeline.set_state(Gst.State.PLAYING)


    
    def pause(self):
        self.pipeline.set_state(Gst.State.PAUSED)

    def play(self):
        self.pipeline.set_state(Gst.State.PLAYING)

# ---------------------------------------------------------
# Functions used to get numpy arrays from GStreamer buffers
# ---------------------------------------------------------

def handle_rgb(map_info, width, height):
    # The copy() method is used to create a copy of the numpy array. This is necessary because the original numpy array is created from buffer data, and it does not own the data it represents. Instead, it's just a view of the buffer's data.
    return np.ndarray(shape=(height, width, 3), dtype=np.uint8, buffer=map_info.data)

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
    if not isinstance(pipeline, Gst.Pipeline):
        print("The provided object is not a GStreamer Pipeline")
        return

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
    gstreamer_app = GStreamerApp('/dev/video2', AppCallback())
    gstreamer_app.app_callback = dummy_app_callback
    gstreamer_app.data_collection_callback = dummy_data_collection_callback
    gstreamer_app.create_pipeline()
    gstreamer_app.run()