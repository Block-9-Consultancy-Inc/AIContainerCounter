project('gst-plugin-frameindexer', 'c',
  version : '1.0.0',
  meson_version : '>=0.54.0', # Updated to common modern version
  default_options : ['warning_level=1',
                     'c_std=c11'])

gst_api_version = '1.0'
gst_dep = dependency('gstreamer-' + gst_api_version, version : '>=1.16',
  fallback : ['gstreamer', 'gst_dep'])
gst_base_dep = dependency('gstreamer-base-' + gst_api_version, version : '>=1.16',
  fallback : ['gstreamer-base', 'gst_base_dep'])

# Add these dependencies:
gst_video_dep = dependency('gstreamer-video-1.0', version : '>=1.16', required : true)
gst_audio_dep = dependency('gstreamer-audio-1.0', version : '>=1.16', required : true)
# For other basic GObject things
glib_dep = dependency('glib-2.0', version: '>=2.56', required : true)
gobject_dep = dependency('gobject-2.0', version: '>=2.56', required : true)


plugin_sources = [
  'gstframeindexerplugin.c',
  'gstframeindexer.c',
  'gstframeindexmeta.c'
]

# plugin_headers section can remain the same

gstframeindexer = library('gstframeindexer',
  plugin_sources,
  # Add the new dependencies here:
  dependencies : [gst_dep, gst_base_dep, gst_video_dep, gst_audio_dep, glib_dep, gobject_dep],
  install : true,
  # Use meson's built-in GStreamer helper for install path if possible for your meson version
  install_dir : join_paths(get_option('libdir'), 'gstreamer-1.0')
)