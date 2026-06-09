import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import ctypes

# --- ctypes setup for the C helper function ---
# Adjust the library name and path as per your compiled plugin
# This assumes your plugin library is named 'libgstframeindexer.so' (Linux)
# and is in a known location or GStreamer's plugin path.
# If GStreamer has already loaded the plugin, ctypes might find it by its name
# if it's in the process memory. Otherwise, provide a full path.

def load_get_frame_index_from_buffer(libgstframeindexer_so_path: str = "/usr/lib64/gstreamer-1.0/libgstframeindexer.so"):
    # Try to find the loaded GStreamer plugin library
    plugin_name = "gstframeindexer" # The name given in GST_PLUGIN_DEFINE
    gst_plugin = None
    try:
        # This attempts to get a handle to an already loaded library.
        # This is more robust than guessing paths if GStreamer loaded it.
        # However, on some systems, getting a handle this way might be tricky.
        # A more direct way is to know the path to your .so file.
        # For now, let's assume a direct path if simple loading by name fails.
        try:
            gst_plugin = ctypes.CDLL(libgstframeindexer_so_path) # Linux example
        except OSError:
            # Fallback: You might need to find the full path if not in standard search paths
            # or if the above doesn't work.
            # For development, you might know where your .so is.
            # e.g., current_dir = os.path.dirname(os.path.abspath(__file__))
            # plugin_path = os.path.join(current_dir,"../build/gst-plugin-frameindexer/.libs", f"lib{plugin_name}.so") # Example path
            # gst_plugin = ctypes.CDLL(plugin_path)
            # This part highly depends on your build setup and where the .so is located.
            # If GStreamer finds your plugin via GST_PLUGIN_PATH, the OS loader might also find it.
            print(f"Warning: Could not load lib{plugin_name}.so directly by name. "
                "Ensure it's in LD_LIBRARY_PATH or provide a full path for ctypes.")
            # As a last resort if you know GStreamer loaded it and symbols are global:
            # gst_plugin = ctypes.CDLL(None) # Access symbols in the current process

            # For a plugin GStreamer loads, its symbols are usually in the global namespace.
            gst_plugin = ctypes.CDLL(None) # Try loading symbols from the current process

    except OSError as e:
        print(f"Error loading C plugin library for ctypes: {e}")
        gst_plugin = None
        # Exit or handle gracefully if the helper function is critical

    get_index_func = None
    if not gst_plugin:
        return None
    try:
        get_index_func = gst_plugin.gst_frame_indexer_get_index_from_buffer
        get_index_func.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)] # GstBuffer* is void*, guint*
        get_index_func.restype = ctypes.c_bool # gboolean is usually bool/int
        print("Successfully setup ctypes for gst_frame_indexer_get_index_from_buffer")
    except AttributeError:
        print("Error: Function gst_frame_indexer_get_index_from_buffer not found in C library.")
        print("Ensure it's defined, exported, and the library is loaded correctly.")
        get_index_func = None

    def get_frame_index_from_buffer(buffer):
        frame_index_out = ctypes.c_uint() # Create a C unsigned int
        # Gst.Buffer is a GObject Introspection wrapper.
        # buffer.__gpointer__ gives the address of the underlying C GstBuffer*.
        buffer_ptr = ctypes.c_void_p(hash(buffer))
        
        success = get_index_func(buffer_ptr, ctypes.byref(frame_index_out))
        
        if success:
            retrieved_index = frame_index_out.value
            # print(f"Probe: Retrieved Frame Index from C Meta: {retrieved_index} (PTS: {buffer.pts / Gst.SECOND:.3f}s)")
            return retrieved_index
        else:
            # print(f"Probe: GstFrameIndexMeta not found on buffer (PTS: {buffer.pts / Gst.SECOND:.3f}s)")
            return None
    return get_frame_index_from_buffer
