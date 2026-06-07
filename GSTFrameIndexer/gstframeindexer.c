#include "gstframeindexer.h"

// Declare a static GstDebugCategory variable
GST_DEBUG_CATEGORY_STATIC (gst_frame_indexer_debug_category);

// Define GST_CAT_DEFAULT to make this the default category for logging macros in this file
#define GST_CAT_DEFAULT gst_frame_indexer_debug_category

/* Define an enum for the signals */
enum
{
  SIGNAL_RESET_FRAME_INDEX,
  LAST_SIGNAL
};

/* Define an array for the signal IDs */
static guint gst_frame_indexer_signals[LAST_SIGNAL] = { 0 };

/* Element GObject type definition */
G_DEFINE_TYPE (GstFrameIndexer, gst_frame_indexer, GST_TYPE_BASE_TRANSFORM);

/* --- GObject methods --- */

static void
gst_frame_indexer_init (GstFrameIndexer * self)
{
  // Initialize current_frame_index to 0.
  // The first frame processed will get index 0.
  self->current_frame_index = 0;
  g_mutex_init (&self->index_lock);
  GST_DEBUG_OBJECT (self, "Initialized with frame index 0");
}

static void
gst_frame_indexer_finalize (GObject * object)
{
  GstFrameIndexer *self = GST_FRAME_INDEXER (object);
  g_mutex_clear (&self->index_lock);
  GST_DEBUG_OBJECT (self, "Finalized");
  G_OBJECT_CLASS (gst_frame_indexer_parent_class)->finalize (object);
}

/* --- GstBaseTransform methods --- */

// This function is called for each buffer that passes through the element.
// GstBaseTransform ensures that the buffer passed here is writable.
static GstFlowReturn
gst_frame_indexer_transform_ip (GstBaseTransform * trans, GstBuffer * buf)
{
  GstFrameIndexer *self = GST_FRAME_INDEXER (trans);
  guint index_to_apply;

  g_mutex_lock (&self->index_lock);
  index_to_apply = self->current_frame_index;
  self->current_frame_index++; // Prepare for next frame
  g_mutex_unlock (&self->index_lock);

  // Add our custom metadata to the buffer
  if (!gst_buffer_add_frame_index_meta (buf, index_to_apply)) {
    GST_WARNING_OBJECT (self, "Failed to add frame index metadata to buffer!");
    // Decide if this is a critical error. For now, let the buffer pass.
  } else {
    GST_LOG_OBJECT (self, "Applied frame index %u", index_to_apply);
  }

  return GST_FLOW_OK;
}


/* --- Signal Handlers --- */
// This can be called via g_signal_emit_by_name(element, "reset-frame-index", NULL);
static void
gst_frame_indexer_reset_signal_handler (GstFrameIndexer *self)
{
  g_mutex_lock (&self->index_lock);
  self->current_frame_index = 0;
  g_mutex_unlock (&self->index_lock);
  GST_INFO_OBJECT (self, "Frame index has been reset to 0 by signal.");
}


/* --- Class Initialization --- */

static void
gst_frame_indexer_class_init (GstFrameIndexerClass * klass)
{
  GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
  GstElementClass *element_class = GST_ELEMENT_CLASS (klass);
  GstBaseTransformClass *base_transform_class = GST_BASE_TRANSFORM_CLASS (klass);

  // Initialize the debug category
  GST_DEBUG_CATEGORY_INIT (gst_frame_indexer_debug_category, /* Category variable */
      "frameindexer",        /* Category name (used in GST_DEBUG env var) */
      0,                     /* Color for output (0 = default) */
      "Frame Indexer Element"/* Description */
  );

  gst_element_class_set_static_metadata (element_class,
      "Frame Indexer",                        // Long name
      "Filter/Metadata",                      // Klass
      "Adds a custom frame index to buffers", // Description
      "Your Name <your.email@example.com>");  // Author

  // Pad Templates: Accepts any caps and passes them through
  GstPadTemplate *sink_templ = gst_pad_template_new ("sink",
      GST_PAD_SINK, GST_PAD_ALWAYS, GST_CAPS_ANY);
  gst_element_class_add_pad_template (element_class, sink_templ);

  GstPadTemplate *src_templ = gst_pad_template_new ("src",
      GST_PAD_SRC, GST_PAD_ALWAYS, GST_CAPS_ANY);
  gst_element_class_add_pad_template (element_class, src_templ);

  // Override GObject methods
  gobject_class->finalize = gst_frame_indexer_finalize;

  // Override GstBaseTransform methods
  // We use transform_ip for in-place modification (adding metadata)
  base_transform_class->transform_ip = GST_DEBUG_FUNCPTR (gst_frame_indexer_transform_ip);
  // If we don't want GstBaseTransform to ever make a copy for us (because we only add meta),
  // we could potentially explore gst_base_transform_set_passthrough.
  // However, adding metadata *does* require the buffer to be writable.
  // GstBaseTransform's transform_ip handles making the buffer writable if it isn't already.
  
  // Install signals
  /**
   * GstFrameIndexer::reset-frame-index:
   *
   * Action signal to reset the internal frame counter back to 0.
   * The next frame processed after this signal will receive index 0.
   */
//   gst_frame_indexer_signals[SIGNAL_RESET_FRAME_INDEX] =
//       g_signal_new ("reset-frame-index", G_TYPE_FROM_CLASS (klass),
//       G_SIGNAL_RUN_LAST | G_SIGNAL_ACTION,
//       G_STRUCT_OFFSET (GstFrameIndexerClass, reset_frame_index_signal_handler), // Class handler offset
//       NULL, NULL, NULL, G_TYPE_NONE, 0); // No parameters for this signal

//   // Provide a default class handler for the signal, can be overridden by derived classes
//   // For a G_SIGNAL_ACTION, this often directly calls the implementation.
//   klass->reset_frame_index_signal_handler = gst_frame_indexer_reset_signal_handler;

    // In gst_frame_indexer_class_init, replace the signal registration part with:
    gst_frame_indexer_signals[SIGNAL_RESET_FRAME_INDEX] =
    g_signal_new_class_handler ("reset-frame-index", // Signal name
                G_TYPE_FROM_CLASS (klass), // Owner GType
                G_SIGNAL_RUN_LAST | G_SIGNAL_ACTION, // Signal flags
                G_CALLBACK(gst_frame_indexer_reset_signal_handler),
                NULL, // Accumulator
                NULL, // Accumulator data
                g_cclosure_marshal_VOID__VOID, // Default marshaller for VOID_VOID
                G_TYPE_NONE, // Return type
                0);          // Number of parameters

    // Connect the default handler for this signal
    // g_signal_new_class_handler (G_TYPE_FROM_CLASS(klass),
    //                         g_signal_lookup("reset-frame-index", G_TYPE_FROM_CLASS(klass)),
    //                         G_CALLBACK(gst_frame_indexer_reset_signal_handler));

}