import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:ai_container_counter/src/rust/frb_generated.dart';
import 'package:texture_rgba_renderer/texture_rgba_renderer.dart';

Future<void> main() async {
  await RustLib.init();
  final Stream<String> eventStream = setEventStreamSink();
  final Stream<FramePayload> detectionEventStream =
      setDetectionEventStreamSink();
  eventStream.listen((data) {
    print('DART: $data');
  });
  runApp(MyApp(
    eventStream: eventStream,
    detectionEventStream: detectionEventStream,
  ));
}

class MyApp extends StatefulWidget {
  final Stream<String> eventStream;
  final Stream<FramePayload> detectionEventStream;
  const MyApp({
    super.key,
    required this.eventStream,
    required this.detectionEventStream,
  });

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  late Socket socket;

  int? _textureId;
  bool playingVideo = true;

  @override
  void initState() {
    super.initState();

    _initializeTextureAndSocket();
  }

  @override
  void dispose() {
    socket.dispose();
    super.dispose();
  }

  Future<void> _initializeTextureAndSocket() async {
    if (_textureId != null) return;
    var textureRenderer = TextureRgbaRenderer();

    // Initialize main texture
    const int textureKeyMain = 0;
    await textureRenderer.closeTexture(textureKeyMain);

    _textureId = await textureRenderer.createTexture(textureKeyMain);
    setState(() {});
    final texturePointer = await textureRenderer.getTexturePtr(textureKeyMain);

    initializeFlutterTexture(texturePtr: BigInt.from(texturePointer));

    socket = newSocket();

    bool didConnect = await socket.connectToSocketServer(
        serverAddress: 'http://localhost:5000');

    if (didConnect) {
      print('DART: socket has connected to server successfully');
    } else {
      print(
          'DART: socket unable to connect to server trying again every 2 seconds');
      bool connected = false;
      while (!connected) {
        await Future.delayed(const Duration(seconds: 2));
        connected = await socket.connectToSocketServer(
            serverAddress: 'http://localhost:5000');
        if (connected) {
          print('DART: socket has connected to server successfully');
        } else {
          print(
              'DART: socket unable to connect to server trying again every 2 seconds');
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        primaryColor: Colors.teal,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.teal,
          brightness: Brightness.light,
        ).copyWith(secondary: Colors.tealAccent),
      ),
      home: Scaffold(
        appBar: AppBar(
          backgroundColor: Colors.white,
          title: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4.0),
            child: Image.asset(
              'lib/res/recyclorobo-logo.png',
              height: 85,
            ),
          ),
        ),
        backgroundColor: Colors.white,
        body: Center(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const Spacer(),
              Expanded(
                flex: 4,
                child: StreamBuilder(
                  stream: widget.detectionEventStream,
                  builder: (context, snapshot) => AutoSizeText(
                    'Count: ${snapshot.hasData ? snapshot.data!.totalOut : 0}',
                    style: const TextStyle(
                      fontWeight: FontWeight.w500,
                      fontSize: 40,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
              const Spacer(),
              if (_textureId != null)
                Expanded(
                  flex: 30,
                  child: AspectRatio(
                    aspectRatio: 1920 / 1080,
                    child: Texture(
                        textureId: _textureId!,
                        filterQuality: FilterQuality.medium),
                  ),
                )
              else
                const Expanded(
                  child: Text('Texture id is null'),
                ),
              const Spacer(),
              Expanded(
                flex: 2,
                child: ElevatedButton(
                  onPressed: () {
                    socket.emitEvent(
                      event: 'reset-count',
                      data: 'reset-count',
                    );
                  },
                  child: const Text('Submit Count'),
                ),
              ),
              const Spacer(),
            ],
          ),
        ),
        floatingActionButton: FloatingActionButton(
          onPressed: () {
            setShowingVideo(showingVideo: !playingVideo);
            setState(() {
              playingVideo = !playingVideo;
            });
          },
          child: !playingVideo
              ? const Icon(Icons.play_arrow)
              : const Icon(Icons.stop),
        ),
      ),
    );
  }
}
