#ifndef __GST_FRAME_INDEX_META_H__
#define __GST_FRAME_INDEX_META_H__

#include <gst/gst.h>

G_BEGIN_DECLS

// A unique name for the metadata implementation
#define GST_FRAME_INDEX_META_IMPL_NAME "GstFrameIndexMeta"
// A unique GType for the metadata API
#define GST_FRAME_INDEX_META_API_TYPE (gst_frame_index_meta_api_get_type())

typedef struct _GstFrameIndexMeta GstFrameIndexMeta;

struct _GstFrameIndexMeta {
  GstMeta meta;     // Must be the first field
  guint frame_index;
};

// Function to get the GType of the metadata API
GType gst_frame_index_meta_api_get_type (void);

// Function to get the GstMetaInfo for this metadata
const GstMetaInfo *gst_frame_index_meta_get_info (void);

// Helper function to add this metadata to a buffer
// Returns the GstFrameIndexMeta if successful, NULL otherwise.
GstFrameIndexMeta *gst_buffer_add_frame_index_meta (GstBuffer *buffer,
                                                    guint frame_index);

// Helper function to retrieve this metadata from a buffer
// Returns the GstFrameIndexMeta if found, NULL otherwise.
#define gst_buffer_get_frame_index_meta(b) \
  ((GstFrameIndexMeta*)gst_buffer_get_meta((b), GST_FRAME_INDEX_META_API_TYPE))

G_END_DECLS

#endif /* __GST_FRAME_INDEX_META_H__ */