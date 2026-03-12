import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:ai_container_counter/src/utils/datetime_utils.dart';
import 'package:ai_container_counter/src/widgets/category_count_displayer.dart';
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class PreviousBatchListView extends StatelessWidget {
  const PreviousBatchListView({super.key});

  @override
  Widget build(BuildContext context) {
    return StreamBuilder(
      stream: context.read<GlobalState>().batchGlobalStateEventStream.stream,
      builder: (context, snapshot) => (snapshot.data?.batches.isEmpty ?? true)
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
              itemCount: snapshot.data!.batches.length,
              itemBuilder: (context, index) {
                return ListTile(
                  onTap: () {
                    final selectedBatch = snapshot.data!.batches[index];
                    final actualIndex = snapshot.data!.batches.length - index;
                    final batchDuration = selectedBatch.timeSubmitted
                        .difference(selectedBatch.timeStarted);
                    showDialog(
                      context: context,
                      builder: (builderContext) => AlertDialog(
                        title: Text(
                          'Batch $actualIndex',
                          style: TextStyle(
                            fontSize: 60,
                            height: 0.75,
                            color: Theme.of(context).colorScheme.inversePrimary,
                          ),
                        ),
                        content: SizedBox(
                          height: 300,
                          width: 850,
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
                                    Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        AutoSizeText(
                                          '${selectedBatch.count.count}',
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
                                        if (selectedBatch.count.countAccuracy !=
                                            null) ...[
                                          const SizedBox(height: 30),
                                          AutoSizeText(
                                            '${selectedBatch.count.countAccuracy!.toStringAsFixed(2)}%',
                                            style: TextStyle(
                                              fontWeight: FontWeight.w500,
                                              fontSize: 50,
                                              height: 0.75,
                                              color: Theme.of(context)
                                                  .colorScheme
                                                  .primary
                                                  .withAlpha(
                                                      (0.8 * 255).toInt()),
                                            ),
                                          ),
                                        ],
                                      ],
                                    ),
                                    const SizedBox(width: 75),
                                    Expanded(
                                      child: CategoryCountDisplayer(
                                        count: selectedBatch.count,
                                        scale: 0.75,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 30),
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
                                  'Time Submitted: ${selectedBatch.timeSubmitted.timeAgo()}',
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
                    'Batch ${snapshot.data!.batches.length - index}: ${snapshot.data!.batches[index].count.count}',
                    style: TextStyle(
                      color: Theme.of(context)
                          .colorScheme
                          .primary
                          .withAlpha((0.7 * 255).toInt()),
                      fontSize: 40,
                    ),
                  ),
                  subtitle: Text(
                    snapshot.data!.batches[index].timeSubmitted.timeAgo(),
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
