import 'package:ai_container_counter/src/models/batch.dart';
import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:ai_container_counter/src/utils/datetime_utils.dart';
import 'package:ai_container_counter/src/widgets/category_count_display.dart';
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class PreviousBatchListView extends StatelessWidget {
  const PreviousBatchListView({super.key});

  @override
  Widget build(BuildContext context) {
    return Selector<GlobalState, List<Batch>>(
      selector: (context, globalState) => globalState.previousBatches,
      builder: (context, previousBatches, child) => previousBatches.isEmpty
          ? Center(
              child: Text(
                'No previous batches today',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 50,
                  color: Theme.of(context).colorScheme.inversePrimary,
                ),
              ),
            )
          : ListView.builder(
              itemCount: previousBatches.length,
              itemBuilder: (context, index) {
                final actualIndex = previousBatches.length - 1 - index;
                return ListTile(
                  onTap: () {
                    final selectedBatch = previousBatches[actualIndex];
                    final batchDuration = selectedBatch.time.difference(
                        actualIndex == 0
                            ? context.read<GlobalState>().timeStarted
                            : previousBatches[actualIndex - 1].time);
                    showDialog(
                      context: context,
                      builder: (builderContext) => AlertDialog(
                        title: Text(
                          'Batch ${actualIndex + 1}',
                          style: TextStyle(
                            fontSize: 60,
                            height: 0.75,
                            color: Theme.of(context).colorScheme.inversePrimary,
                          ),
                        ),
                        content: SizedBox(
                          height: 250,
                          width: 700,
                          child: Padding(
                            padding: const EdgeInsets.only(left: 50),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.center,
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
                                    Expanded(
                                      child: CategoryCountDisplay(
                                        classWiseCount:
                                            selectedBatch.classWiseCount,
                                        scale: 0.75,
                                      ),
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
                      color: Theme.of(context).colorScheme.inversePrimary,
                    ),
                  ),
                );
              }),
    );
  }
}
