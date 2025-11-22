### Notes when setting up environment
1. When setting up the environment, always update the BaseSolutions class to take in an imgsz and use that in the call to model.track in extract_tracks function

### How to mock MJPEG camera stream
```
ffmpeg -stream_loop -1 -re -i processed-counting-machine-test-videos/speed-5-1/speed-5-1-1920x1080.avi -c:v copy -f v4l2 /dev/video0
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