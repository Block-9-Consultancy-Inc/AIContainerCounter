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

  Count runningActual = const Count();
  Count runningExpected = const Count();

  final stopWatchTimer = StopWatchTimer()..onStartTimer();

  final timeStarted = DateTime.now();

  List<Batch> previousBatches = [];

  Count? get expectedCount => _expectedCount;
  Count? _expectedCount;
  set expectedCount(Count? newExpectedCount) {
    _expectedCount = newExpectedCount;
    notifyListeners();
  }

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
        time: DateTime.now(),
        actualCount: Count(
            count: detectionEventStream.lastEvent?.totalIn ?? 0,
            classWiseCount: detectionEventStream.lastEvent?.classWiseCount ??
                const [
                  ClassWiseCount(class_: 'can', inCount: 0, outCount: 0),
                  ClassWiseCount(class_: 'plastic', inCount: 0, outCount: 0),
                  ClassWiseCount(class_: 'drinkbox', inCount: 0, outCount: 0),
                  ClassWiseCount(class_: 'gabletop', inCount: 0, outCount: 0),
                  ClassWiseCount(class_: 'pouch', inCount: 0, outCount: 0),
                ]),
        expectedCount: expectedCount,
      ),
    ];

    if (previousBatches.last.expectedCount != null) {
      final expectedClassWiseCount =
          List<ClassWiseCount>.from(runningExpected.classWiseCount);
      for (var i = 0; i < expectedClassWiseCount.length; i++) {
        final category = expectedClassWiseCount[i].class_;
        final newClassWiseCount = previousBatches
            .last.expectedCount!.classWiseCount
            .firstWhere((classWiseCount) => classWiseCount.class_ == category);
        expectedClassWiseCount[i] = ClassWiseCount(
          class_: category,
          inCount: runningExpected.classWiseCount[i].inCount +
              newClassWiseCount.inCount,
          outCount: runningExpected.classWiseCount[i].outCount +
              newClassWiseCount.outCount,
        );
      }
      runningExpected = Count(
        count:
            runningExpected.count + previousBatches.last.expectedCount!.count,
        classWiseCount: expectedClassWiseCount,
      );
    }

    final actualClassWiseCount =
        List<ClassWiseCount>.from(runningActual.classWiseCount);
    for (var i = 0; i < actualClassWiseCount.length; i++) {
      final category = actualClassWiseCount[i].class_;
      final newClassWiseCount = previousBatches.last.actualCount.classWiseCount
          .firstWhere((classWiseCount) => classWiseCount.class_ == category);
      actualClassWiseCount[i] = ClassWiseCount(
        class_: category,
        inCount: actualClassWiseCount[i].inCount + newClassWiseCount.inCount,
        outCount: actualClassWiseCount[i].outCount + newClassWiseCount.outCount,
      );
    }
    runningActual = Count(
      count: runningActual.count + previousBatches.last.actualCount.count,
      classWiseCount: actualClassWiseCount,
    );

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
