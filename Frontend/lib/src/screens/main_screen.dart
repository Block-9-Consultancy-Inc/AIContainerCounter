import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:ai_container_counter/src/screens/real_time_video_stream.dart';
import 'package:ai_container_counter/src/widgets/current_batch_view.dart';
import 'package:ai_container_counter/src/widgets/previous_batch_list_view.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:ai_container_counter/src/api.dart';

class MainScreen extends StatelessWidget {
  const MainScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 120,
        title: Padding(
          padding: const EdgeInsets.symmetric(vertical: 1.0),
          child: context.select<GlobalState, ThemeMode>(
                      (globalState) => globalState.themeMode) ==
                  ThemeMode.light
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
              final globalState = context.read<GlobalState>();
              globalState.themeMode = globalState.themeMode == ThemeMode.light
                  ? ThemeMode.dark
                  : ThemeMode.light;
            },
            iconSize: 80,
            icon: context.select<GlobalState, ThemeMode>(
                        (globalState) => globalState.themeMode) ==
                    ThemeMode.light
                ? const Icon(Icons.dark_mode)
                : const Icon(Icons.light_mode),
          ),
          Builder(builder: (context) {
            return IconButton(
              onPressed: () async {
                await setVideo(context.read<GlobalState>().socket!, true);
                // ignore: use_build_context_synchronously
                await Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (builderContext) => const RealTimeVideoStream(),
                  ),
                );
                // ignore: use_build_context_synchronously
                await setVideo(context.read<GlobalState>().socket!, false);
              },
              iconSize: 80,
              color: Theme.of(context).colorScheme.primary,
              icon: const Icon(Icons.videocam),
            );
          }),
        ],
      ),
      body: Builder(builder: (context) {
        return const Row(
          mainAxisAlignment: MainAxisAlignment.start,
          mainAxisSize: MainAxisSize.max,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 2,
              child: Padding(
                padding: EdgeInsets.only(
                  left: 40,
                  right: 40,
                  bottom: 40,
                ),
                child: CurrentBatchView(),
              ),
            ),
            Expanded(
              child: Padding(
                padding: EdgeInsets.only(
                  left: 40,
                  right: 40,
                ),
                child: PreviousBatchListView(),
              ),
            ),
          ],
        );
      }),
    );
  }
}
