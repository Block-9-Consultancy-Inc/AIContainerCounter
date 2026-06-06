#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <gst/gst.h>
#include "gstframeindexer.h" // Our element header

#define PACKAGE "gst-plugins-frameindexer"

static gboolean
plugin_init (GstPlugin * plugin)
{
  // Register the GstFrameIndexer element
  // The TRUE at the end means it will be rank GST_RANK_NONE (default)
  // You can set a different rank if needed (e.g., GST_RANK_PRIMARY, GST_RANK_SECONDARY)
  if (!gst_element_register (plugin, "frameindexer", GST_RANK_NONE,
          GST_TYPE_FRAME_INDEXER)) {
    GST_ERROR ("Failed to register 'frameindexer' element");
    return FALSE;
  }

  // Initialize custom metadata (ensure its GType is known)
  // Calling get_info() once will trigger its g_once_init and register the meta.
  if (!gst_frame_index_meta_get_info()) {
      GST_ERROR("Failed to initialize GstFrameIndexMeta info.");
      return FALSE;
  }


  GST_INFO ("Plugin 'frameindexer' initialized.");
  return TRUE;
}

GST_PLUGIN_DEFINE (
    GST_VERSION_MAJOR,
    GST_VERSION_MINOR,
    frameindexer, // Plugin name (lowercase, no spaces or special chars)
    "Adds a custom frame index to buffers", // Plugin description
    plugin_init, // Plugin entry point
    "1.0.0", // Version (e.g., "1.0.0")
    "LGPL",          // License
    "gst-plugins-frameindexer",    // Source (e.g., "gst-plugins-frameindexer")
    "http://example.com/" // Origin (e.g., "http://example.com/")
)