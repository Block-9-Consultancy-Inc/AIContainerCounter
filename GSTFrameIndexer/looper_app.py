import gi
gi.require_version('Gst', '1.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gst, GLib
import os
import sys
from time import sleep

# --- Configuration ---
VIDEO_DIRECTORY = "/home/ammanz/Projects/AIContainerCounter/GSTFrameIndexer/videos"  # Directory containing your video files
# Supported video extensions (add more if needed)
SUPPORTED_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts', '.mpg', '.mpeg')

def get_gst_message_type_name(message_type: Gst.MessageType) -> str:
    """
    Returns the string name of a GstMessageType.

    Args:
        message_type: A Gst.MessageType enum value.

    Returns:
        A string representing the name of the message type.
    """
    if not isinstance(message_type, Gst.MessageType):
        # Handle cases where the input might not be a valid GstMessageType
        # For example, if an integer is passed that doesn't map to a type.
        # Gst.message_type_get_name() expects a GstMessageType enum value.
        try:
            # Attempt to cast integer to Gst.MessageType if it's an int
            message_type = Gst.MessageType(message_type)
        except ValueError:
            return f"Invalid GstMessageType value: {message_type}"

    return Gst.message_type_get_name(message_type)

class VideoPlayer:
    def __init__(self, video_dir):
        self.video_files = []
        self.current_video_index = -1
        self.frameindexer = None
        self.playbin = None
        self.loop = GLib.MainLoop()

        self.scan_video_directory(video_dir)

        if not self.video_files:
            print(f"No video files found in directory: {video_dir}")
            sys.exit(1)

        self.setup_pipeline()

    def scan_video_directory(self, video_dir):
        print(f"Scanning for videos in: {os.path.abspath(video_dir)}")
        if not os.path.isdir(video_dir):
            print(f"Error: Directory '{video_dir}' not found.")
            return

        for item in sorted(os.listdir(video_dir)): # Sort for predictable order
            if item.lower().endswith(SUPPORTED_EXTENSIONS):
                self.video_files.append(os.path.join(os.path.abspath(video_dir), item))
        print(f"Found videos: {self.video_files}")

    def setup_pipeline(self):
        # Create playbin
        self.playbin = Gst.ElementFactory.make("playbin3", "player")
        if not self.playbin:
            print("Error: Could not create playbin.")
            sys.exit(1)

        # Create the video sink bin with frameindexer
        # Ensure your frameindexer plugin is installed and visible to GStreamer
        videosink_bin_description = (
            "videoconvert ! "
            "frameindexer name=myframeindexer ! "
            "autovideosink"
        )
        videosink_bin = Gst.parse_bin_from_description(videosink_bin_description, True)
        if not videosink_bin:
            print(f"Error: Could not parse video sink bin: {videosink_bin_description}")
            sys.exit(1)

        self.playbin.set_property("video-sink", videosink_bin)

        # Get a reference to the frameindexer element
        # We need to wait for playbin to construct the sink bin.
        # A robust way is to get it after the pipeline is in PAUSED or PLAYING state,
        # or use the 'deep-element-added' signal on GstBin.
        # For simplicity here, we'll try to get it after setting the first URI.
        # A better approach is to get it from the videosink_bin before assigning to playbin.

        self.frameindexer = videosink_bin.get_by_name("myframeindexer")
        if not self.frameindexer:
            print("Error: Could not get 'myframeindexer' from the custom video sink bin.")
            print("Make sure the 'frameindexer' GStreamer plugin is correctly installed.")
            # Attempt to find it later if it's not available immediately
            # self.playbin.connect("deep-element-added", self.on_deep_element_added)


        # Connect to the 'about-to-finish' signal from playbin
        self.playbin.connect("about-to-finish", self.on_about_to_finish)

        # Setup bus message handling
        bus = self.playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_bus_message)

    # def on_deep_element_added(self, bin, sub_bin, element):
    #     if element.get_name() == "myframeindexer" and not self.frameindexer:
    #         print("Frameindexer found via deep-element-added.")
    #         self.frameindexer = element


    def on_about_to_finish(self, player):
        print("\n--- about-to-finish: Current video ending ---")
        self.play_next_video(player=player)

    def on_bus_message(self, bus, message):
        mtype = message.type
        if mtype == Gst.MessageType.EOS:
            print("\n--- EOS received: Player decided to stop (might be end of playlist if not handled by about-to-finish) ---")
            # For continuous looping, about-to-finish is preferred.
            # If EOS is hit, it usually means playbin gave up or an error occurred.
            # We could also trigger play_next_video here if not handled by about-to-finish,
            # but it might lead to double handling.
            # For robustness, let's ensure we loop if about-to-finish didn't catch it or if it's a single file.
            print("EOS: Re-triggering next video to ensure loop.")
            self.play_next_video() # Try to play next to ensure loop
        elif mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error from {message.src.get_name()}: {err.message}")
            print(f"Debugging information: {debug}")
            self.loop.quit()
        elif mtype == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            print(f"Warning from {message.src.get_name()}: {err.message}")
        # You can watch for ASYNC_DONE to know when state changes are complete
        elif mtype == Gst.MessageType.ASYNC_DONE:
            print("Async done (e.g., state change complete).")
        elif mtype == Gst.MessageType.ELEMENT:
            # Some elements like playbin post custom "ELEMENT" messages.
            # For example, GstPlayFlags::element_eos (gstplayflags.h) might be posted.
            structure = message.get_structure()
            if structure and structure.has_name("GstPlayFlags"): # Example, might need specific check
                 print(f"Element message: {structure.to_string()}")
        elif mtype == Gst.MessageType.STREAM_START:
            self.frameindexer.emit("reset-frame-index")



    def play_next_video(self, player=None):
        if not self.video_files:
            print("No videos in playlist to play.")
            self.loop.quit()
            return

        self.current_video_index = (self.current_video_index + 1) % len(self.video_files)
        next_uri = GLib.filename_to_uri(self.video_files[self.current_video_index], None)

        print(f"Playing next: {self.video_files[self.current_video_index]} (URI: {next_uri})")
        playbin = player if player is not None else self.playbin
        playbin.set_property("uri", next_uri)
        # Playbin should automatically go to PLAYING. If it was in PLAYING, setting URI re-triggers.
        # If it reached EOS and went to PAUSED/READY, explicitly set to PLAYING.
        playbin.set_state(Gst.State.PLAYING)



    def run(self):
        if not self.video_files:
            return

        self.play_next_video() # Start playing the first video
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("Loop interrupted by user.")
        finally:
            print("Shutting down pipeline.")
            self.playbin.set_state(Gst.State.NULL)

def main():
    Gst.init(None)
    # Create the directory if it doesn't exist for the user
    if not os.path.exists(VIDEO_DIRECTORY):
        try:
            os.makedirs(VIDEO_DIRECTORY)
            print(f"Created directory '{VIDEO_DIRECTORY}'. Please add some video files there.")
        except OSError as e:
            print(f"Error creating directory {VIDEO_DIRECTORY}: {e}")
            sys.exit(1)

    player = VideoPlayer(VIDEO_DIRECTORY)
    if player.video_files:
        player.run()
    else:
        print(f"Exiting as no video files were found or directory '{VIDEO_DIRECTORY}' could not be accessed.")


if __name__ == "__main__":
    # To see logs from your frameindexer C plugin:
    # export GST_DEBUG=frameindexer:5,playbin:3,python:3
    # (python:3 might show GStreamer Python binding logs if issues arise there)
    main()