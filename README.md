### Notes when setting up environment
1. When setting up the environment, always update the BaseSolutions class to take in an imgsz and use that in the call to model.track in extract_tracks function

### How to mock MJPEG camera stream
```
ffmpeg -stream_loop -1 -re -i file.avi -c:v copy -f v4l2 /dev/video0
```


### Collecting Test Videos
```
gst-launch-1.0 v4l2src device=/dev/video1 ! "image/jpeg,width=1920,height=1080,framerate=60/1" ! jpegdec ! videoconvert ! x264enc bitrate=10000 ! mp4mux ! filesink location=speed-5-1.mp4 -e

ffmpeg -f v4l2 -input_format mjpeg -i /dev/video0 -framerate 60 -video_size 1920x1080 -vcodec mjpeg -qscale 1 test-video.avi
```

### Checking FPS
```
ffprobe -v 0 -of csv=p=0 -select_streams V:0 -show_entries stream=r_frame_rate speed-5-1.mp4
```

### Convert MJPEG avi to H.264 mp4

gst-launch-1.0 filesrc location=processed-counting-machine-test-videos/speed-5-1/speed-5-1-1920x1080.avi ! decodebin ! x264enc quantizer=18 speed-preset=9 ! mp4mux ! filesink location=test.mp4

### Convert H.264 mp4 to MJPEG avi

gst-launch-1.0 filesrc location=test.mp4 ! decodebin ! jpegenc ! avimux ! filesink location=test.avi
