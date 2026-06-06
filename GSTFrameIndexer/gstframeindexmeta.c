#include "gstframeindexmeta.h"

GType
gst_frame_index_meta_api_get_type (void)
{
  static volatile GType type = 0;
  static const gchar *tags[] = { "video", "audio", "text", NULL }; // Applicable to various stream types

  if (g_once_init_enter (&type)) {
    GType _type = gst_meta_api_type_register (GST_FRAME_INDEX_META_IMPL_NAME "API", tags);
    g_once_init_leave (&type, _type);
  }


  return type;
}

static gboolean
gst_frame_index_meta_init_func (GstMeta * meta, gpointer params, GstBuffer * buffer)
{
  GstFrameIndexMeta *fimeta = (GstFrameIndexMeta *) meta;
  fimeta->frame_index = 0; // Default initialization
  return TRUE;
}

static void
gst_frame_index_meta_free_func (GstMeta * meta, GstBuffer * buffer)
{
  // GstFrameIndexMeta *fimeta = (GstFrameIndexMeta *) meta;
  // No dynamically allocated resources in GstFrameIndexMeta to free here
}

static gboolean
gst_frame_index_meta_transform_func (GstBuffer * dest_buf, GstMeta * src_meta_gst,
    GstBuffer * src_buf, GQuark type, gpointer data)
{
  GstFrameIndexMeta *src_meta = (GstFrameIndexMeta *) src_meta_gst;
  GstFrameIndexMeta *dest_meta;

  if (GST_META_TRANSFORM_IS_COPY (type)) {
    // Add a new instance of our metadata to the destination buffer
    dest_meta = gst_buffer_add_frame_index_meta (dest_buf, src_meta->frame_index);
    if (!dest_meta) {
      GST_WARNING ("Failed to copy GstFrameIndexMeta");
      return FALSE;
    }
    // The frame_index is already set by gst_buffer_add_frame_index_meta if it uses the passed param
    // Or, if gst_buffer_add_frame_index_meta just adds an uninitialized meta:
    // dest_meta->frame_index = src_meta->frame_index;
  } else {
    // For other transformation types, we don't do anything specific here.
    // Depending on the transformation, one might want to modify, drop, or
    // create new metadata. For this example, we only handle copy.
    return TRUE; // Or FALSE if the transformation isn't supported/handled
  }
  return TRUE;
}

const GstMetaInfo *
gst_frame_index_meta_get_info (void)
{
  static const GstMetaInfo *meta_info = NULL;
  static gsize _init = 0;

  if (g_once_init_enter (&_init)) {
    meta_info = gst_meta_register (GST_FRAME_INDEX_META_API_TYPE,
        GST_FRAME_INDEX_META_IMPL_NAME,
        sizeof (GstFrameIndexMeta),
        gst_frame_index_meta_init_func,
        gst_frame_index_meta_free_func,
        gst_frame_index_meta_transform_func);
    g_once_init_leave (&_init, 1);
  }
  return meta_info;
}

GstFrameIndexMeta *
gst_buffer_add_frame_index_meta (GstBuffer * buffer, guint frame_index)
{
  GstFrameIndexMeta *fimeta;

  // Ensure our meta info is registered and available
  g_return_val_if_fail (gst_frame_index_meta_get_info () != NULL, NULL);

  fimeta = (GstFrameIndexMeta *) gst_buffer_add_meta (buffer,
      gst_frame_index_meta_get_info (), NULL);

  if (!fimeta) {
    GST_WARNING ("Failed to add GstFrameIndexMeta to buffer");
    return NULL;
  }

  fimeta->frame_index = frame_index;
  return fimeta;
}