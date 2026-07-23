import socketio
from turbojpeg import TurboJPEG
from supervision import VideoSink, VideoInfo
import base64
import sys
import signal


def counter_video_client(video_sink: VideoSink):
    jpeg = TurboJPEG()
    client = socketio.Client()
    client.connect(url='http://192.168.1.99:5000', namespaces=['/'], retry=True)

    @client.on('detection_event')
    def on_detection_event(message):
        print(f'got detection event!')
        encoded_frame = message.get('encoded_frame')
        base64_decoded = base64.b64decode(encoded_frame)
        decoded_frame = jpeg.decode(base64_decoded)
        video_sink.write_frame(decoded_frame)

    def finish(signum=None, frame=None):
        print(f'got signum:{signum}, disconnnecting!')
        client.disconnect()
        
    signal.signal(signal.SIGINT, finish)

    client.wait()

if __name__ == '__main__':
    with VideoSink(sys.argv[1], VideoInfo(
            2560,
            1440,
            1
        )) as video_sink:
        counter_video_client(video_sink)