import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:ai_container_counter/src/utils/calculation_utils.dart';
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
              Row(
                children: [
                  Selector<GlobalState, int?>(
                    selector: (context, state) => state.expectedCount == null
                        ? null
                        : state.runningExpected.count,
                    builder: (context, runningExpectedCount, child) => Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        AutoSizeText(
                          context.select<GlobalState, String>(
                              (state) => '${state.runningActual.count}'),
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
                        if (runningExpectedCount != null) ...[
                          const SizedBox(height: 30),
                          AutoSizeText(
                            computeCountAccuracy(
                              context.select<GlobalState, int>(
                                  (state) => state.runningActual.count),
                              runningExpectedCount,
                            ),
                            style: TextStyle(
                              fontWeight: FontWeight.w500,
                              fontSize: 50,
                              height: 0.75,
                              color: Theme.of(context)
                                  .colorScheme
                                  .primary
                                  .withOpacity(0.8),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 75),
                  CategoryCountDisplayer(
                    classWiseCount:
                        context.select<GlobalState, List<ClassWiseCount>>(
                            (state) => state.runningActual.classWiseCount),
                    expectedClassWiseCount:
                        context.select<GlobalState, List<ClassWiseCount>?>(
                            (state) => state.expectedCount == null
                                ? null
                                : state.runningExpected.classWiseCount),
                    scale: 0.75,
                    endPadding: 300,
                  ),
                ],
              ),
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
                            .withOpacity(0.7),
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
                          '${snapshot.hasData ? snapshot.data!.totalIn : 0}',
                          style: TextStyle(
                            fontWeight: FontWeight.w500,
                            fontSize: 150,
                            height: 0.75,
                            color: Theme.of(context)
                                .colorScheme
                                .primary
                                .withOpacity(0.8),
                          ),
                        ),
                        if (context.select<GlobalState, bool>(
                            (state) => state.expectedCount != null)) ...[
                          const SizedBox(height: 30),
                          AutoSizeText(
                            computeCountAccuracy(
                              snapshot.hasData ? snapshot.data!.totalIn : 0,
                              context.select<GlobalState, int>(
                                (state) => state.expectedCount!.count,
                              ),
                            ),
                            style: TextStyle(
                              fontWeight: FontWeight.w500,
                              fontSize: 50,
                              height: 0.75,
                              color: Theme.of(context)
                                  .colorScheme
                                  .primary
                                  .withOpacity(0.8),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(width: 100),
                    Expanded(
                      child: CategoryCountDisplayer(
                        classWiseCount: snapshot.data?.classWiseCount ?? [],
                        expectedClassWiseCount:
                            context.select<GlobalState, List<ClassWiseCount>?>(
                                (state) => state.expectedCount?.classWiseCount),
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
