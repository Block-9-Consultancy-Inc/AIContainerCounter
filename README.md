### Notes when setting up environment
1. When setting up the environment, always update the BaseSolutions class to take in an imgsz and use that in the call to model.track in extract_tracks function

### How to mock MJPEG camera stream
```
ffmpeg -stream_loop -1 -re -i processed-counting-machine-test-videos/speed-5-1/speed-5-1-1920x1080.avi -c:v copy -f v4l2 /dev/video0
```