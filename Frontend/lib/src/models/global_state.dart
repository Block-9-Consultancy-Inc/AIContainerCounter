import 'package:ai_container_counter/src/models/last_cached_stream.dart';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:ai_container_counter/src/rust/api/models/count.dart';
import 'package:flutter/material.dart';
import 'package:stop_watch_timer/stop_watch_timer.dart';
import 'package:texture_rgba_renderer/texture_rgba_renderer.dart';

class GlobalState extends ChangeNotifier {
  final String backendHost;
  final int backendPort;
  final LastEventCachedStream<Count> detectionEventStream;
  final LastEventCachedStream<String> eventStream;
  final LastEventCachedStream<StateUpdate> stateUpdateEventStream;
  Socket? socket;
  int? textureId;

  final stopWatchTimer = StopWatchTimer()..onStartTimer();

  final timeStarted = DateTime.now();

  bool viewingRealtimeVideoFeed = false;

  PipelineState get currentPipelineState => _currentPipelineState;

  PipelineState _currentPipelineState = PipelineState.running;

  void updateCurrentPipelineState(BuildContext context) {
    stateUpdateEventStream.stream
        .where((e) =>
            e is StateUpdate_PipelineStateUpdate ||
            e is StateUpdate_StopConfirmationUpdate)
        .listen((stateUpdate) async {
      if (stateUpdate is StateUpdate_StopConfirmationUpdate) {
        print('SHOWED DIALOG');
        showDialog(
            // ignore: use_build_context_synchronously
            context: context,
            useRootNavigator: true,
            barrierDismissible: false,
            builder: (context) => const AlertDialog(
                  title: Text('Stop Confirmation'),
                  content: Text('Press the stop button again to confirm.'),
                ));
        await Future.delayed(const Duration(milliseconds: 1500));
        // ignore: use_build_context_synchronously
        Navigator.of(context).pop();
        print('POPPED DIALOG');
        return;
      } else if (stateUpdate is StateUpdate_ResetConfirmationUpdate) {
        print('SHOWED DIALOG');
        showDialog(
            // ignore: use_build_context_synchronously
            context: context,
            useRootNavigator: true,
            barrierDismissible: false,
            builder: (context) => const AlertDialog(
                  title: Text('Submit Batch Confirmation'),
                  content: Text('Press the submit button again to confirm.'),
                ));
        await Future.delayed(const Duration(milliseconds: 1500));
        // ignore: use_build_context_synchronously
        Navigator.of(context).pop();
        print('POPPED DIALOG');
        return;
      }

      stateUpdate = stateUpdate as StateUpdate_PipelineStateUpdate;
      if (_currentPipelineState != PipelineState.running &&
          stateUpdate.newState == PipelineState.running) {
        stopWatchTimer.onStartTimer();
      } else if (_currentPipelineState == PipelineState.running &&
          stateUpdate.newState == PipelineState.paused) {
        stopWatchTimer.onStopTimer();
      } else if (_currentPipelineState == PipelineState.running &&
          stateUpdate.newState == PipelineState.stopped) {
        stopWatchTimer.onResetTimer();
      }

      _currentPipelineState = stateUpdate.newState;
      notifyListeners();
    });
  }

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

  GlobalState(
      {required this.detectionEventStream,
      required this.eventStream,
      required this.stateUpdateEventStream,
      required this.backendHost,
      required this.backendPort}) {
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

    bool didConnect = await socket!.connectToSocketServer(
        serverAddress: 'http://$backendHost:$backendPort');

    if (didConnect) {
      print('DART: socket has connected to server successfully');
      socket!.emitEvent(event: 'init-prev-batches', data: 'init-prev-batches');
    } else {
      print(
          'DART: socket unable to connect to server trying again every 2 seconds');
      bool connected = false;
      while (!connected) {
        await Future.delayed(const Duration(seconds: 2));
        connected = await socket!.connectToSocketServer(
            serverAddress: 'http://$backendHost:$backendPort');
        if (connected) {
          print('DART: socket has connected to server successfully');
          socket!
              .emitEvent(event: 'init-prev-batches', data: 'init-prev-batches');
        } else {
          print(
              'DART: socket unable to connect to server trying again every 2 seconds');
        }
      }
    }
  }

  Future<void> submitBatch() async {
    socket?.emitEvent(
      event: 'reset-count',
      data: 'reset-count',
    );
    stopWatchTimer.onResetTimer();
    stopWatchTimer.onStartTimer();
    notifyListeners();
    // try {
    //   printReceipt(lastBatchGlobalState!.batches.length,
    //       lastBatchGlobalState!.batches.first);
    // } catch (e) {
    //   print('Unable to print receipt: $e');
    // }
  }
}
