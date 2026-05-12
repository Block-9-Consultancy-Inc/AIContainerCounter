import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:ai_container_counter/src/rust/api/models/count.dart';
import 'package:ai_container_counter/src/widgets/category_count_displayer.dart';
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:stop_watch_timer/stop_watch_timer.dart';

class CurrentBatchView extends StatelessWidget {
  const CurrentBatchView({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      mainAxisSize: MainAxisSize.max,
      children: [
        Expanded(
          flex: 15,
          child: ElevatedButton(
            style: ButtonStyle(
                minimumSize: const WidgetStatePropertyAll(Size.infinite),
                shape: WidgetStatePropertyAll(RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20)))),
            onPressed: () async {
              final close = await showDialog<bool>(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('Submit Batch Confirmation'),
                  content:
                      const Text('Are you sure you want to close this bag?'),
                  actions: [
                    ElevatedButton(
                        onPressed: () {
                          Navigator.of(context).pop(true);
                        },
                        child: const Text('Close')),
                    TextButton(
                        onPressed: () {
                          Navigator.of(context).pop(false);
                        },
                        child: const Text('Cancel')),
                  ],
                ),
              );

              if (close ?? false) {
                // ignore: use_build_context_synchronously
                context.read<GlobalState>().submitBatch();
              }
            },
            child: const AutoSizeText(
              'Submit Batch',
              maxLines: 2,
              style: TextStyle(fontSize: 45),
            ),
          ),
        ),
        const Spacer(flex: 5),
        Expanded(
          flex: 20,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                'Total Daily Count',
                style: TextStyle(
                  fontSize: 40,
                  height: 0.75,
                  color: Theme.of(context).colorScheme.inversePrimary,
                ),
              ),
              const SizedBox(height: 10),
              StreamBuilder(
                  stream: context
                      .read<GlobalState>()
                      .stateUpdateEventStream
                      .stream
                      .where((e) => e is StateUpdate_BatchGlobalState)
                      .map((e) => e as StateUpdate_BatchGlobalState),
                  builder: (context, snapshot) {
                    return Row(
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            AutoSizeText(
                              '${snapshot.data?.batchGlobalState.todaySummary.count.count.toInt() ?? 0}',
                              style: TextStyle(
                                fontWeight: FontWeight.w500,
                                fontSize: 100,
                                height: 0.75,
                                color: Theme.of(context)
                                    .colorScheme
                                    .primary
                                    .withAlpha((0.7 * 255).toInt()),
                              ),
                            ),
                            if (snapshot.data?.batchGlobalState.todaySummary
                                    .count.countAccuracy !=
                                null) ...[
                              const SizedBox(height: 30),
                              AutoSizeText(
                                '${snapshot.data!.batchGlobalState.todaySummary.count.countAccuracy!.toStringAsFixed(2)}%',
                                style: TextStyle(
                                  fontWeight: FontWeight.w500,
                                  fontSize: 50,
                                  height: 0.75,
                                  color: Theme.of(context)
                                      .colorScheme
                                      .primary
                                      .withAlpha((0.8 * 255).toInt()),
                                ),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(width: 75),
                        Expanded(
                          child: CategoryCountDisplayer(
                            count: snapshot
                                .data?.batchGlobalState.todaySummary.count,
                            scale: 0.75,
                            endPadding: 300,
                          ),
                        ),
                      ],
                    );
                  }),
            ],
          ),
        ),
        Expanded(
          flex: 10,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    'Current Batch Elapsed Time',
                    style: TextStyle(
                      fontSize: 25,
                      height: 0.75,
                      color: Theme.of(context).colorScheme.inversePrimary,
                    ),
                  ),
                  const SizedBox(height: 10),
                  StreamBuilder(
                      stream:
                          context.read<GlobalState>().stopWatchTimer.rawTime,
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
                                .withAlpha((0.7 * 255).toInt()),
                          ),
                        );
                      }),
                ],
              ),
              const SizedBox(width: 50),
              Selector<GlobalState, PipelineState>(
                selector: (context, e) => e.currentPipelineState,
                builder: (context, value, child) => value ==
                        PipelineState.stopped
                    ? FloatingActionButton(
                        onPressed: () => context
                            .read<GlobalState>()
                            .socket
                            ?.emitEvent(event: 'play', data: 'play'),
                        child: const Icon(Icons.play_arrow))
                    : Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          if (value == PipelineState.paused)
                            FloatingActionButton(
                                onPressed: () => context
                                    .read<GlobalState>()
                                    .socket
                                    ?.emitEvent(event: 'play', data: 'play'),
                                child: const Icon(Icons.play_arrow)),
                          if (value == PipelineState.running)
                            FloatingActionButton(
                                onPressed: () => context
                                    .read<GlobalState>()
                                    .socket
                                    ?.emitEvent(event: 'pause', data: 'pause'),
                                child: const Icon(Icons.pause)),
                          const SizedBox(width: 20),
                          FloatingActionButton(
                              onPressed: () async {
                                final stop = await showDialog<bool>(
                                  context: context,
                                  builder: (context) => AlertDialog(
                                    title: const Text('Stop Confirmation'),
                                    content: const Text(
                                        'Are you sure you want to stop for the day?'),
                                    actions: [
                                      ElevatedButton(
                                          onPressed: () {
                                            Navigator.of(context).pop(true);
                                          },
                                          child: const Text('Stop')),
                                      TextButton(
                                          onPressed: () {
                                            Navigator.of(context).pop(false);
                                          },
                                          child: const Text('Cancel')),
                                    ],
                                  ),
                                );

                                if (stop ?? false) {
                                  // ignore: use_build_context_synchronously
                                  context
                                      .read<GlobalState>()
                                      .socket
                                      ?.emitEvent(event: 'stop', data: 'stop');
                                }
                              },
                              child: const Icon(Icons.stop)),
                        ],
                      ),
              ),
            ],
          ),
        ),
        Expanded(
          flex: 20,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              AutoSizeText(
                'Current Count',
                style: TextStyle(
                  fontSize: 40,
                  height: 0.75,
                  color: Theme.of(context).colorScheme.inversePrimary,
                ),
              ),
              const SizedBox(height: 10),
              StreamBuilder(
                stream: context.read<GlobalState>().detectionEventStream.stream,
                builder: (context, snapshot) => Row(
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        AutoSizeText(
                          '${snapshot.hasData ? snapshot.data!.count : 0}',
                          style: TextStyle(
                            fontWeight: FontWeight.w500,
                            fontSize: 150,
                            height: 0.75,
                            color: Theme.of(context)
                                .colorScheme
                                .primary
                                .withAlpha((0.8 * 255).toInt()),
                          ),
                        ),
                        if (context.select<GlobalState, bool>(
                            (state) => state.expectedCount != null)) ...[
                          const SizedBox(height: 30),
                          AutoSizeText(
                            '${snapshot.hasData ? snapshot.data?.countAccuracy?.toStringAsFixed(2) ?? '0.0' : '0.0'}%',
                            style: TextStyle(
                              fontWeight: FontWeight.w500,
                              fontSize: 50,
                              height: 0.75,
                              color: Theme.of(context)
                                  .colorScheme
                                  .primary
                                  .withAlpha((0.8 * 255).toInt()),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(width: 100),
                    Expanded(
                      child: CategoryCountDisplayer(
                        count: snapshot.data,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
