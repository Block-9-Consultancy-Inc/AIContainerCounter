import 'dart:async';

import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:ai_container_counter/src/models/last_cached_stream.dart';
import 'package:ai_container_counter/src/screens/main_screen.dart';
import 'package:flutter/material.dart';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:ai_container_counter/src/rust/frb_generated.dart';
import 'package:provider/provider.dart';
import 'package:window_manager/window_manager.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

late final bool showCategories;

Future<void> main() async {
  await RustLib.init();
  await dotenv.load();
  showCategories = dotenv.env['SHOW_CATEGORIES'] == 'true';
  final eventStream = LastEventCachedStream(setEventStreamSink());
  final detectionEventStream =
      LastEventCachedStream(setDetectionEventStreamSink());
  final stateUpdateEventStream =
      LastEventCachedStream(setJsonResponseStreamSink());
  WidgetsFlutterBinding.ensureInitialized();
  WindowManager.instance.ensureInitialized();
  WindowManager.instance.setTitleBarStyle(TitleBarStyle.hidden);
  WindowManager.instance.maximize();
  runApp(ChangeNotifierProvider(
      create: (context) => GlobalState(
            detectionEventStream: detectionEventStream,
            eventStream: eventStream,
            stateUpdateEventStream: stateUpdateEventStream,
          ),
      child: const AIContainerCounterApp()));
}

class AIContainerCounterApp extends StatelessWidget {
  const AIContainerCounterApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      themeMode: context.select<GlobalState, ThemeMode>(
          (globalState) => globalState.themeMode),
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
      home: const MainScreen(),
    );
  }
}
