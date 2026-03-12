import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:ai_container_counter/src/rust/models/count.dart';
import 'package:ai_container_counter/src/widgets/category_count_displayer.dart';
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:stop_watch_timer/stop_watch_timer.dart';

class CurrentBatchView extends StatefulWidget {
  const CurrentBatchView({super.key});

  @override
  State<CurrentBatchView> createState() => _CurrentBatchViewState();
}

class _CurrentBatchViewState extends State<CurrentBatchView> {
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
            onPressed: context.read<GlobalState>().submitBatch,
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
                        CategoryCountDisplayer(
                          count: snapshot
                              .data?.batchGlobalState.todaySummary.count,
                          scale: 0.75,
                          endPadding: 300,
                        ),
                      ],
                    );
                  }),
            ],
          ),
        ),
        Expanded(
          flex: 10,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
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
                  stream: context.read<GlobalState>().stopWatchTimer.rawTime,
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
        ),
        Expanded(
          flex: 20,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
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
