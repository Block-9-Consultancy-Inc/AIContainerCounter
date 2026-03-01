import 'package:ai_container_counter/src/api.dart';
import 'package:ai_container_counter/src/models/batch.dart';
import 'package:ai_container_counter/src/models/last_cached_stream.dart';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:flutter/material.dart';
import 'package:stop_watch_timer/stop_watch_timer.dart';
import 'package:texture_rgba_renderer/texture_rgba_renderer.dart';

class GlobalState extends ChangeNotifier {
  final LastEventCachedStream<FramePayload> detectionEventStream;
  final LastEventCachedStream<String> eventStream;
  Socket? socket;
  int? textureId;

  int runningTotal = 0;
  final runningClassWiseCount = [
    const ClassWiseCount(class_: 'can', inCount: 0, outCount: 0),
    const ClassWiseCount(class_: 'plastic', inCount: 0, outCount: 0),
    const ClassWiseCount(class_: 'drinkbox', inCount: 0, outCount: 0),
    const ClassWiseCount(class_: 'gabletop', inCount: 0, outCount: 0),
    const ClassWiseCount(class_: 'pouch', inCount: 0, outCount: 0),
  ];

  final stopWatchTimer = StopWatchTimer()..onStartTimer();

  final timeStarted = DateTime.now();

  List<Batch> previousBatches = [];

  ThemeMode get themeMode => _themeMode;
  ThemeMode _themeMode = ThemeMode.dark;
  set themeMode(ThemeMode newThemeMode) {
    _themeMode = newThemeMode;
    notifyListeners();
  }

  GlobalState({
    required this.detectionEventStream,
    required this.eventStream,
  }) {
    _initializeTextureAndSocket();
  }

  Future<void> _initializeTextureAndSocket() async {
    if (textureId != null) return;
    var textureRenderer = TextureRgbaRenderer();

    // Initialize main texture
    const int textureKeyMain = 0;
    await textureRenderer.closeTexture(textureKeyMain);

    textureId = await textureRenderer.createTexture(textureKeyMain);
    final texturePointer = await textureRenderer.getTexturePtr(textureKeyMain);

    initializeFlutterTexture(texturePtr: BigInt.from(texturePointer));

    socket = newSocket();

    bool didConnect = await socket!
        .connectToSocketServer(serverAddress: 'http://localhost:5000');

    if (didConnect) {
      print('DART: socket has connected to server successfully');
    } else {
      print(
          'DART: socket unable to connect to server trying again every 2 seconds');
      bool connected = false;
      while (!connected) {
        await Future.delayed(const Duration(seconds: 2));
        connected = await socket!
            .connectToSocketServer(serverAddress: 'http://localhost:5000');
        if (connected) {
          print('DART: socket has connected to server successfully');
        } else {
          print(
              'DART: socket unable to connect to server trying again every 2 seconds');
        }
      }
    }
  }

  Future<void> submitBatch() async {
    previousBatches = [
      ...previousBatches,
      Batch(
          count: detectionEventStream.lastEvent?.totalIn ?? 0,
          time: DateTime.now(),
          classWiseCount: detectionEventStream.lastEvent?.classWiseCount ?? []),
    ];
    runningTotal += previousBatches.last.count;
    for (var i = 0; i < runningClassWiseCount.length; i++) {
      final category = runningClassWiseCount[i].class_;
      final newClassWiseCount = previousBatches.last.classWiseCount
          .firstWhere((classWiseCount) => classWiseCount.class_ == category);
      runningClassWiseCount[i] = ClassWiseCount(
        class_: category,
        inCount: runningClassWiseCount[i].inCount + newClassWiseCount.inCount,
        outCount:
            runningClassWiseCount[i].outCount + newClassWiseCount.outCount,
      );
    }
    socket?.emitEvent(
      event: 'reset-count',
      data: 'reset-count',
    );
    stopWatchTimer.onResetTimer();
    stopWatchTimer.onStartTimer();
    notifyListeners();
    try {
      printReceipt(previousBatches.length, previousBatches.last);
    } catch (e) {
      print('Unable to print receipt: $e');
    }
  }
}
