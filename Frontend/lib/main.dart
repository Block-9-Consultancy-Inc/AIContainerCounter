import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:ai_container_counter/src/rust/frb_generated.dart';

Future<void> main() async {
  await RustLib.init();
  final Stream<String> eventStream = setEventStreamSink();
  final Stream<Uint8List> detectionEventStream = setDetectionEventStreamSink();
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
  final Stream<Uint8List> detectionEventStream;
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

  @override
  void initState() {
    super.initState();
    socket = newSocket();

    socket
        .connectToSocketServer(serverAddress: 'http://localhost:5000')
        .then((didConnect) async {
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

      int i = 1;
      while (true) {
        await socket.emitEvent(event: 'test', data: 'test sent from dart! $i');
        i++;
        await Future.delayed(const Duration(seconds: 2));
      }
    });
  }

  @override
  void dispose() {
    socket.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('AI Container Counting Machine')),
        body: Center(
          child: StreamBuilder(
            stream: widget.detectionEventStream,
            builder: (context, snapshot) => snapshot.hasData
                ? Image.memory(snapshot.data!, gaplessPlayback: true)
                : const SizedBox.shrink(),
          ),
        ),
      ),
    );
  }
}
