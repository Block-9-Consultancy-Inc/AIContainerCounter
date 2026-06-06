#ifndef __GST_FRAME_INDEXER_H__
#define __GST_FRAME_INDEXER_H__

#include <gst/base/gstbasetransform.h>
#include "gstframeindexmeta.h" // Include our custom metadata header

G_BEGIN_DECLS

#define GST_TYPE_FRAME_INDEXER (gst_frame_indexer_get_type())
G_DECLARE_FINAL_TYPE (GstFrameIndexer, gst_frame_indexer, GST, FRAME_INDEXER, GstBaseTransform)

struct _GstFrameIndexer {
  GstBaseTransform parent;

  guint current_frame_index;
  GMutex index_lock; // For thread-safe access to current_frame_index
};

G_END_DECLS

#endif /* __GST_FRAME_INDEXER_H__ */