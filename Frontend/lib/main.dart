import 'dart:async';

import 'package:ai_container_counter/src/api.dart';
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:ai_container_counter/src/rust/frb_generated.dart';
import 'package:stop_watch_timer/stop_watch_timer.dart';
import 'package:texture_rgba_renderer/texture_rgba_renderer.dart';
import 'package:window_manager/window_manager.dart';

extension DateTimeExtension on DateTime {
  String timeAgo({bool numericDates = true}) {
    final date2 = DateTime.now();
    final difference = date2.difference(this);

    if ((difference.inDays / 7).floor() >= 1) {
      return (numericDates) ? '1 week ago' : 'Last week';
    } else if (difference.inDays >= 2) {
      return '${difference.inDays} days ago';
    } else if (difference.inDays >= 1) {
      return (numericDates) ? '1 day ago' : 'Yesterday';
    } else if (difference.inHours >= 2) {
      return '${difference.inHours} hours ago';
    } else if (difference.inHours >= 1) {
      return (numericDates) ? '1 hour ago' : 'An hour ago';
    } else if (difference.inMinutes >= 2) {
      return '${difference.inMinutes} minutes ago';
    } else if (difference.inMinutes >= 1) {
      return (numericDates) ? '1 minute ago' : 'A minute ago';
    } else if (difference.inSeconds >= 3) {
      return '${difference.inSeconds} seconds ago';
    } else {
      return 'Just now';
    }
  }
}

class LastEventCachedStream<T> {
  final Stream<T> _stream;
  T? lastEvent;

  Stream<T> get stream => _stream;

  LastEventCachedStream(Stream<T> stream)
      : _stream = stream.asBroadcastStream() {
    _stream.forEach((event) {
      lastEvent = event;
    });
  }
}

Future<void> main() async {
  await RustLib.init();
  final eventStream = LastEventCachedStream(setEventStreamSink());
  final detectionEventStream =
      LastEventCachedStream(setDetectionEventStreamSink());
  eventStream.stream.listen((data) {
    print('DART: $data');
  });
  WidgetsFlutterBinding.ensureInitialized();
  WindowManager.instance.ensureInitialized();
  WindowManager.instance.setTitleBarStyle(TitleBarStyle.hidden);
  WindowManager.instance.maximize();
  runApp(MyApp(
    eventStream: eventStream,
    detectionEventStream: detectionEventStream,
  ));
}

class MyApp extends StatefulWidget {
  final LastEventCachedStream<String> eventStream;
  final LastEventCachedStream<FramePayload> detectionEventStream;
  const MyApp({
    super.key,
    required this.eventStream,
    required this.detectionEventStream,
  });

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  ThemeMode _themeMode = ThemeMode.light;
  late Socket socket;
  final previousBatches =
      <({int count, DateTime time, List<ClassWiseCount> classWiseCount})>[];
  int runningTotal = 0;
  int runningAluminum = 0;
  int runningPlastic = 0;
  int runningGableTop = 0;
  int runningDrinkBox = 0;
  int runningGlass = 0;
  int runningPouch = 0;

  final timeStarted = DateTime.now();
  final StopWatchTimer stopWatchTimer = StopWatchTimer();
  int? _textureId;

  @override
  void initState() {
    super.initState();
    _initializeTextureAndSocket();
    stopWatchTimer.onStartTimer();
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

  Future<void> setVideo(bool on) async {
    await socket.emitEvent(event: 'set-video', data: on.toString());
  }

  Future<void> _submitBatch() async {
    previousBatches.add((
      count: widget.detectionEventStream.lastEvent?.totalOut ?? 0,
      time: DateTime.now(),
      classWiseCount:
          widget.detectionEventStream.lastEvent?.classWiseCount ?? []
    ));
    runningTotal =
        previousBatches.fold(0, (value, element) => value + element.count);
    runningAluminum = previousBatches.fold(
        0,
        (value, element) =>
            value +
            element.classWiseCount
                .firstWhere((e) => e.class_ == 'aluminum',
                    orElse: () => const ClassWiseCount(
                        class_: 'aluminum', inCount: 0, outCount: 0))
                .outCount);
    runningPlastic = previousBatches.fold(
        0,
        (value, element) =>
            value +
            element.classWiseCount
                .firstWhere((e) => e.class_ == 'plastic',
                    orElse: () => const ClassWiseCount(
                        class_: 'plastic', inCount: 0, outCount: 0))
                .outCount);
    runningGableTop = previousBatches.fold(
        0,
        (value, element) =>
            value +
            element.classWiseCount
                .firstWhere((e) => e.class_ == 'gabletop',
                    orElse: () => const ClassWiseCount(
                        class_: 'gabletop', inCount: 0, outCount: 0))
                .outCount);
    runningDrinkBox = previousBatches.fold(
        0,
        (value, element) =>
            value +
            element.classWiseCount
                .firstWhere((e) => e.class_ == 'drinkbox',
                    orElse: () => const ClassWiseCount(
                        class_: 'drinkbox', inCount: 0, outCount: 0))
                .outCount);
    runningGlass = previousBatches.fold(
        0,
        (value, element) =>
            value +
            element.classWiseCount
                .firstWhere((e) => e.class_ == 'glass',
                    orElse: () => const ClassWiseCount(
                        class_: 'glass', inCount: 0, outCount: 0))
                .outCount);
    runningPouch = previousBatches.fold(
        0,
        (value, element) =>
            value +
            element.classWiseCount
                .firstWhere((e) => e.class_ == 'pouch',
                    orElse: () => const ClassWiseCount(
                        class_: 'pouch', inCount: 0, outCount: 0))
                .outCount);
    setState(() {});
    socket.emitEvent(
      event: 'reset-count',
      data: 'reset-count',
    );
    printReceipt(previousBatches.last);
    stopWatchTimer.onResetTimer();
    stopWatchTimer.onStartTimer();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      themeMode: _themeMode,
      theme: ThemeData(
        primaryColor: const Color.fromRGBO(56, 182, 255, 1),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color.fromRGBO(56, 182, 255, 1),
          brightness: Brightness.light,
        ).copyWith(secondary: const Color.fromRGBO(56, 182, 255, 1)),
      ),
      darkTheme: ThemeData(
        primaryColor: const Color.fromRGBO(56, 182, 255, 1),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color.fromRGBO(56, 182, 255, 1),
          brightness: Brightness.dark,
        ).copyWith(secondary: const Color.fromRGBO(56, 182, 255, 1)),
      ),
      home: Scaffold(
        appBar: AppBar(
          toolbarHeight: 120,
          title: Padding(
            padding: const EdgeInsets.symmetric(vertical: 1.0),
            child: _themeMode == ThemeMode.light
                ? Image.asset(
                    'lib/res/recyclorobo-logo.png',
                    height: 55,
                  )
                : Image.asset(
                    'lib/res/recyclorobo-logo-dark.png',
                    height: 55,
                  ),
          ),
          actions: [
            IconButton(
              onPressed: () {
                setState(() {
                  _themeMode = _themeMode == ThemeMode.light
                      ? ThemeMode.dark
                      : ThemeMode.light;
                });
              },
              iconSize: 80,
              icon: _themeMode == ThemeMode.light
                  ? const Icon(Icons.dark_mode)
                  : const Icon(Icons.light_mode),
            ),
            Builder(builder: (context) {
              return IconButton(
                onPressed: () async {
                  await setVideo(true);
                  // ignore: use_build_context_synchronously
                  await Navigator.of(context).push(MaterialPageRoute(
                      builder: (builderContext) => Scaffold(
                            appBar: AppBar(
                              automaticallyImplyLeading: false,
                              backgroundColor: Colors.black.withOpacity(0.0),
                              title: Row(
                                children: [
                                  IconButton(
                                    onPressed: () =>
                                        Navigator.of(builderContext).pop(),
                                    icon: const Icon(Icons.close),
                                    color:
                                        const Color.fromRGBO(56, 182, 255, 1),
                                  ),
                                  const SizedBox(width: 10),
                                  ElevatedButton(
                                      onPressed: _submitBatch,
                                      child: const Text('Submit Batch')),
                                ],
                              ),
                            ),
                            extendBodyBehindAppBar: true,
                            body: Center(
                              child: AspectRatio(
                                aspectRatio: 1920 / 1080,
                                child: Texture(
                                  textureId: _textureId!,
                                  filterQuality: FilterQuality.medium,
                                ),
                              ),
                            ),
                          )));
                  await setVideo(false);
                },
                iconSize: 80,
                color: Theme.of(context).colorScheme.primary,
                icon: const Icon(Icons.videocam),
              );
            }),
          ],
        ),
        body: Builder(builder: (context) {
          return Row(
            mainAxisAlignment: MainAxisAlignment.start,
            mainAxisSize: MainAxisSize.max,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                flex: 2,
                child: Padding(
                  padding: const EdgeInsets.only(
                    left: 40,
                    right: 40,
                    bottom: 40,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.end,
                    mainAxisSize: MainAxisSize.max,
                    children: [
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.only(bottom: 70),
                          child: ElevatedButton(
                            style: ButtonStyle(
                                minimumSize:
                                    const WidgetStatePropertyAll(Size.infinite),
                                shape: WidgetStatePropertyAll(
                                    RoundedRectangleBorder(
                                        borderRadius:
                                            BorderRadius.circular(20)))),
                            onPressed: _submitBatch,
                            child: const AutoSizeText(
                              'Submit Batch',
                              maxLines: 2,
                              style: TextStyle(fontSize: 80),
                            ),
                          ),
                        ),
                      ),
                      Text(
                        'Total Daily Count',
                        style: TextStyle(
                          fontSize: 40,
                          height: 0.75,
                          color: Theme.of(context).colorScheme.inversePrimary,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          AutoSizeText(
                            '$runningTotal',
                            style: TextStyle(
                              fontWeight: FontWeight.w500,
                              fontSize: 100,
                              height: 0.75,
                              color: Theme.of(context)
                                  .colorScheme
                                  .primary
                                  .withOpacity(0.7),
                            ),
                          ),
                          const SizedBox(width: 75),
                          CategoryCountDisplay(
                            aluminum: runningAluminum,
                            plastic: runningPlastic,
                            gableTop: runningGableTop,
                            drinkBox: runningDrinkBox,
                            glass: runningGlass,
                            pouch: runningPouch,
                            scale: 0.75,
                            endPadding: 300,
                          ),
                        ],
                      ),
                      const SizedBox(height: 50),
                      Text(
                        'Current Batch Elapsed Time',
                        style: TextStyle(
                          fontSize: 40,
                          height: 0.75,
                          color: Theme.of(context).colorScheme.inversePrimary,
                        ),
                      ),
                      const SizedBox(height: 10),
                      StreamBuilder(
                          stream: stopWatchTimer.rawTime,
                          builder: (context, snapshot) {
                            return Text(
                              StopWatchTimer.getDisplayTime(
                                snapshot.data ?? 0,
                                hours: false,
                              ),
                              style: TextStyle(
                                fontWeight: FontWeight.w500,
                                fontSize: 40,
                                height: 0.75,
                                color: Theme.of(context)
                                    .colorScheme
                                    .primary
                                    .withOpacity(0.7),
                              ),
                            );
                          }),
                      const SizedBox(height: 20),
                      Text(
                        'Current Count',
                        style: TextStyle(
                          fontSize: 120,
                          height: 0.75,
                          color: Theme.of(context).colorScheme.inversePrimary,
                        ),
                      ),
                      const SizedBox(height: 10),
                      StreamBuilder(
                        stream: widget.detectionEventStream.stream,
                        builder: (context, snapshot) => Row(
                          children: [
                            AutoSizeText(
                              '${snapshot.hasData ? snapshot.data!.totalOut : 0}',
                              style: TextStyle(
                                fontWeight: FontWeight.w500,
                                fontSize: 320,
                                height: 0.75,
                                color: Theme.of(context)
                                    .colorScheme
                                    .primary
                                    .withOpacity(0.8),
                              ),
                            ),
                            const SizedBox(width: 100),
                            CategoryCountDisplay(
                              aluminum: snapshot.data?.classWiseCount
                                      .firstWhere((e) => e.class_ == 'aluminum',
                                          orElse: () => const ClassWiseCount(
                                              class_: 'aluminum',
                                              inCount: 0,
                                              outCount: 0))
                                      .outCount ??
                                  0,
                              plastic: snapshot.data?.classWiseCount
                                      .firstWhere((e) => e.class_ == 'plastic',
                                          orElse: () => const ClassWiseCount(
                                              class_: 'plastic',
                                              inCount: 0,
                                              outCount: 0))
                                      .outCount ??
                                  0,
                              gableTop: snapshot.data?.classWiseCount
                                      .firstWhere((e) => e.class_ == 'gabletop',
                                          orElse: () => const ClassWiseCount(
                                              class_: 'gabletop',
                                              inCount: 0,
                                              outCount: 0))
                                      .outCount ??
                                  0,
                              drinkBox: snapshot.data?.classWiseCount
                                      .firstWhere((e) => e.class_ == 'drinkbox',
                                          orElse: () => const ClassWiseCount(
                                              class_: 'drinkbox',
                                              inCount: 0,
                                              outCount: 0))
                                      .outCount ??
                                  0,
                              glass: snapshot.data?.classWiseCount
                                      .firstWhere((e) => e.class_ == 'glass',
                                          orElse: () => const ClassWiseCount(
                                              class_: 'glass',
                                              inCount: 0,
                                              outCount: 0))
                                      .outCount ??
                                  0,
                              pouch: snapshot.data?.classWiseCount
                                      .firstWhere((e) => e.class_ == 'pouch',
                                          orElse: () => const ClassWiseCount(
                                              class_: 'pouch',
                                              inCount: 0,
                                              outCount: 0))
                                      .outCount ??
                                  0,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(
                    left: 40,
                    right: 40,
                  ),
                  child: previousBatches.isEmpty
                      ? Center(
                          child: Text(
                            'No previous batches today',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 50,
                              color:
                                  Theme.of(context).colorScheme.inversePrimary,
                            ),
                          ),
                        )
                      : ListView.builder(
                          itemCount: previousBatches.length,
                          itemBuilder: (context, index) {
                            final actualIndex =
                                previousBatches.length - 1 - index;
                            return ListTile(
                              onTap: () {
                                final selectedBatch =
                                    previousBatches[actualIndex];
                                final batchDuration = selectedBatch.time
                                    .difference(actualIndex == 0
                                        ? timeStarted
                                        : previousBatches[actualIndex - 1]
                                            .time);
                                showDialog(
                                  context: context,
                                  builder: (builderContext) => AlertDialog(
                                    title: Text(
                                      'Batch ${actualIndex + 1}',
                                      style: TextStyle(
                                        fontSize: 60,
                                        height: 0.75,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .inversePrimary,
                                      ),
                                    ),
                                    content: SizedBox(
                                      height: 250,
                                      width: 700,
                                      child: Padding(
                                        padding:
                                            const EdgeInsets.only(left: 50),
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          mainAxisAlignment:
                                              MainAxisAlignment.center,
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            Text(
                                              'Total Count',
                                              style: TextStyle(
                                                fontSize: 40,
                                                height: 0.75,
                                                color: Theme.of(context)
                                                    .colorScheme
                                                    .inversePrimary,
                                              ),
                                            ),
                                            const SizedBox(height: 10),
                                            Row(
                                              children: [
                                                AutoSizeText(
                                                  '${selectedBatch.count}',
                                                  style: TextStyle(
                                                    fontWeight: FontWeight.w500,
                                                    fontSize: 100,
                                                    height: 0.75,
                                                    color: Theme.of(context)
                                                        .colorScheme
                                                        .primary
                                                        .withOpacity(0.7),
                                                  ),
                                                ),
                                                const SizedBox(width: 75),
                                                CategoryCountDisplay(
                                                  aluminum: selectedBatch
                                                      .classWiseCount
                                                      .firstWhere(
                                                          (e) =>
                                                              e.class_ ==
                                                              'aluminum',
                                                          orElse: () =>
                                                              const ClassWiseCount(
                                                                  class_:
                                                                      'aluminum',
                                                                  inCount: 0,
                                                                  outCount: 0))
                                                      .outCount,
                                                  plastic: selectedBatch
                                                      .classWiseCount
                                                      .firstWhere(
                                                          (e) =>
                                                              e.class_ ==
                                                              'plastic',
                                                          orElse: () =>
                                                              const ClassWiseCount(
                                                                  class_:
                                                                      'plastic',
                                                                  inCount: 0,
                                                                  outCount: 0))
                                                      .outCount,
                                                  gableTop: selectedBatch
                                                      .classWiseCount
                                                      .firstWhere(
                                                          (e) =>
                                                              e.class_ ==
                                                              'gabletop',
                                                          orElse: () =>
                                                              const ClassWiseCount(
                                                                  class_:
                                                                      'gabletop',
                                                                  inCount: 0,
                                                                  outCount: 0))
                                                      .outCount,
                                                  drinkBox: selectedBatch
                                                      .classWiseCount
                                                      .firstWhere(
                                                          (e) =>
                                                              e.class_ ==
                                                              'drinkbox',
                                                          orElse: () =>
                                                              const ClassWiseCount(
                                                                  class_:
                                                                      'drinkbox',
                                                                  inCount: 0,
                                                                  outCount: 0))
                                                      .outCount,
                                                  glass: selectedBatch
                                                      .classWiseCount
                                                      .firstWhere(
                                                          (e) =>
                                                              e.class_ ==
                                                              'glass',
                                                          orElse: () =>
                                                              const ClassWiseCount(
                                                                  class_:
                                                                      'glass',
                                                                  inCount: 0,
                                                                  outCount: 0))
                                                      .outCount,
                                                  pouch: selectedBatch
                                                      .classWiseCount
                                                      .firstWhere(
                                                          (e) =>
                                                              e.class_ ==
                                                              'pouch',
                                                          orElse: () =>
                                                              const ClassWiseCount(
                                                                  class_:
                                                                      'pouch',
                                                                  inCount: 0,
                                                                  outCount: 0))
                                                      .outCount,
                                                  scale: 0.75,
                                                ),
                                              ],
                                            ),
                                            const SizedBox(height: 10),
                                            Text(
                                              'Time Elapsed: ${batchDuration.inMinutes} m ${batchDuration.inSeconds - batchDuration.inMinutes * 60} s',
                                              style: TextStyle(
                                                fontSize: 18,
                                                height: 0.75,
                                                color: Theme.of(context)
                                                    .colorScheme
                                                    .inversePrimary,
                                              ),
                                            ),
                                            const SizedBox(height: 10),
                                            Text(
                                              'Time Submitted: ${selectedBatch.time.timeAgo()}',
                                              style: TextStyle(
                                                fontSize: 18,
                                                height: 0.75,
                                                color: Theme.of(context)
                                                    .colorScheme
                                                    .inversePrimary,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                );
                              },
                              title: Text(
                                'Batch ${actualIndex + 1}: ${previousBatches[actualIndex].count}',
                                style: TextStyle(
                                  color: Theme.of(context)
                                      .colorScheme
                                      .primary
                                      .withOpacity(0.7),
                                  fontSize: 40,
                                ),
                              ),
                              subtitle: Text(
                                previousBatches[actualIndex].time.timeAgo(),
                                style: TextStyle(
                                  fontSize: 30,
                                  color: Theme.of(context)
                                      .colorScheme
                                      .inversePrimary,
                                ),
                              ),
                            );
                          }),
                ),
              ),
            ],
          );
        }),
      ),
    );
  }
}

class CategoryCountDisplay extends StatelessWidget {
  final double scale;
  final double endPadding;
  final int aluminum;
  final int plastic;
  final int gableTop;
  final int drinkBox;
  final int glass;
  final int pouch;
  const CategoryCountDisplay({
    super.key,
    this.scale = 1.0,
    this.endPadding = 0,
    this.aluminum = 0,
    this.plastic = 0,
    this.gableTop = 0,
    this.drinkBox = 0,
    this.glass = 0,
    this.pouch = 0,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
        child: Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Aluminum: $aluminum',
                  style: TextStyle(
                    fontSize: 30 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Plastic: $plastic',
                  style: TextStyle(
                    fontSize: 30 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Gable Top: $gableTop',
                  style: TextStyle(
                    fontSize: 30 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Drink Box: $drinkBox',
                  style: TextStyle(
                    fontSize: 30 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Glass: $glass',
                  style: TextStyle(
                    fontSize: 30 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Pouch: $pouch',
                  style: TextStyle(
                    fontSize: 30 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
            ],
          ),
        ),
        SizedBox(width: endPadding)
      ],
    ));
  }
}
