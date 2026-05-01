import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:ai_container_counter/src/rust/api/models/count.dart';
import 'package:ai_container_counter/src/screens/real_time_video_stream.dart';
import 'package:ai_container_counter/src/widgets/current_batch_view.dart';
import 'package:ai_container_counter/src/widgets/previous_batch_list_view.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:ai_container_counter/src/api.dart';

extension StringExtension on String {
  String capitalize() {
    return "${this[0].toUpperCase()}${substring(1).toLowerCase()}";
  }
}

String? expectedCountValidator(value) {
  if (value?.isEmpty ?? true) {
    return 'This field is mandatory';
  }

  final parsedValue = int.tryParse(value!);
  if (parsedValue == null) {
    return 'Needs to be a valid integer';
  }

  if (parsedValue < 0) {
    return 'Needs to be a positive integer';
  }

  return null;
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  @override
  void initState() {
    super.initState();

    context.read<GlobalState>().updateCurrentPipelineState();
    context
        .read<GlobalState>()
        .stateUpdateEventStream
        .stream
        .where((e) => e is StateUpdate_ButtonPressed)
        .listen((stateUpdate) async {
      // ignore: use_build_context_synchronously
      final globalState = context.read<GlobalState>();
      final buttonPressedStateUpdate = stateUpdate as StateUpdate_ButtonPressed;
      if (buttonPressedStateUpdate.buttonId == 1) {
        globalState.stopWatchTimer.onResetTimer();
        globalState.stopWatchTimer.onStartTimer();
      } else if (buttonPressedStateUpdate.buttonId == 2) {
        if (globalState.viewingRealtimeVideoFeed) {
          // ignore: use_build_context_synchronously
          Navigator.of(context).pop();
          await setVideo(globalState.socket!, false);
          globalState.viewingRealtimeVideoFeed = false;
        } else {
          await setVideo(globalState.socket!, true);
          globalState.viewingRealtimeVideoFeed = true;
          // ignore: use_build_context_synchronously
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (builderContext) => const RealTimeVideoStream(),
            ),
          );
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        Scaffold(
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
                onPressed: () async {
                  final globalState = context.read<GlobalState>();
                  Count? newExpectedCount;
                  final formKey = GlobalKey<FormState>();
                  final canController = TextEditingController(
                      text: globalState.expectedCount?.expectedCanCount
                          .toString());
                  final plasticController = TextEditingController(
                      text: globalState.expectedCount?.expectedPlasticCount
                          .toString());
                  final gabletopController = TextEditingController(
                      text: globalState.expectedCount?.expectedGabletopCount
                          .toString());
                  final drinkboxController = TextEditingController(
                      text: globalState.expectedCount?.expectedDrinkboxCount
                          .toString());
                  final pouchController = TextEditingController(
                      text: globalState.expectedCount?.expectedPouchCount
                          .toString());

                  int getNewTotal() {
                    final can = int.tryParse(canController.text) ?? 0;
                    final plastic = int.tryParse(plasticController.text) ?? 0;
                    final gabletop = int.tryParse(gabletopController.text) ?? 0;
                    final drinkbox = int.tryParse(drinkboxController.text) ?? 0;
                    final pouch = int.tryParse(pouchController.text) ?? 0;

                    return can + plastic + gabletop + drinkbox + pouch;
                  }

                  int currentTotal = getNewTotal();

                  final shouldClear = await showDialog<bool>(
                    context: context,
                    builder: (builderContext) =>
                        StatefulBuilder(builder: (context, setState) {
                      return Form(
                        key: formKey,
                        child: SimpleDialog(
                          title: const Text('Update expected count'),
                          contentPadding: const EdgeInsets.symmetric(
                            vertical: 15,
                            horizontal: 15,
                          ),
                          children: [
                            ElevatedButton(
                              style: ButtonStyle(
                                backgroundColor: const WidgetStatePropertyAll(
                                    Colors.redAccent),
                                foregroundColor:
                                    const WidgetStatePropertyAll(Colors.white),
                                overlayColor: WidgetStatePropertyAll(
                                    Colors.red.withAlpha((0.3 * 255).toInt())),
                              ),
                              onPressed: () {
                                Navigator.of(builderContext).pop(true);
                              },
                              child: const Text('Clear'),
                            ),
                            TextFormField(
                              controller: canController,
                              keyboardType: TextInputType.number,
                              validator: expectedCountValidator,
                              decoration:
                                  const InputDecoration(labelText: 'Can'),
                              onChanged: (_) {
                                setState(() {
                                  currentTotal = getNewTotal();
                                });
                              },
                            ),
                            TextFormField(
                              controller: plasticController,
                              keyboardType: TextInputType.number,
                              validator: expectedCountValidator,
                              decoration:
                                  const InputDecoration(labelText: 'Plastic'),
                              onChanged: (_) {
                                setState(() {
                                  currentTotal = getNewTotal();
                                });
                              },
                            ),
                            TextFormField(
                              controller: drinkboxController,
                              keyboardType: TextInputType.number,
                              validator: expectedCountValidator,
                              decoration:
                                  const InputDecoration(labelText: 'Drinkbox'),
                              onChanged: (_) {
                                setState(() {
                                  currentTotal = getNewTotal();
                                });
                              },
                            ),
                            TextFormField(
                              controller: gabletopController,
                              keyboardType: TextInputType.number,
                              validator: expectedCountValidator,
                              decoration:
                                  const InputDecoration(labelText: 'Gabletop'),
                              onChanged: (_) {
                                setState(() {
                                  currentTotal = getNewTotal();
                                });
                              },
                            ),
                            TextFormField(
                              controller: pouchController,
                              keyboardType: TextInputType.number,
                              validator: expectedCountValidator,
                              decoration:
                                  const InputDecoration(labelText: 'Pouch'),
                              onChanged: (_) {
                                setState(() {
                                  currentTotal = getNewTotal();
                                });
                              },
                            ),
                            const SizedBox(height: 2),
                            Text('Current Total: $currentTotal'),
                            const SizedBox(height: 2),
                            ElevatedButton(
                              onPressed: () {
                                if (formKey.currentState!.validate()) {
                                  newExpectedCount = Count(
                                    count: BigInt.from(0),
                                    canCount: BigInt.from(0),
                                    plasticCount: BigInt.from(0),
                                    drinkboxCount: BigInt.from(0),
                                    gabletopCount: BigInt.from(0),
                                    pouchCount: BigInt.from(0),
                                    expectedCanCount: BigInt.from(
                                        int.tryParse(canController.text) ?? 0),
                                    expectedPlasticCount: BigInt.from(
                                        int.tryParse(plasticController.text) ??
                                            0),
                                    expectedDrinkboxCount: BigInt.from(
                                        int.tryParse(drinkboxController.text) ??
                                            0),
                                    expectedGabletopCount: BigInt.from(
                                        int.tryParse(gabletopController.text) ??
                                            0),
                                    expectedPouchCount: BigInt.from(
                                        int.tryParse(pouchController.text) ??
                                            0),
                                  );
                                  context
                                      .read<GlobalState>()
                                      .socket
                                      ?.emitNewExpectedCategoryCount(data: {
                                    'can': BigInt.from(
                                        int.parse(canController.text)),
                                    'plastic': BigInt.from(
                                        int.parse(plasticController.text)),
                                    'drinkbox': BigInt.from(
                                        int.parse(drinkboxController.text)),
                                    'gabletop': BigInt.from(
                                        int.parse(gabletopController.text)),
                                    'pouch': BigInt.from(
                                        int.parse(pouchController.text)),
                                  });
                                  Navigator.of(builderContext).pop(false);
                                }
                              },
                              child: const Text('Apply'),
                            ),
                          ],
                        ),
                      );
                    }),
                  );
                  if (shouldClear != null) {
                    globalState.expectedCount = newExpectedCount;
                    if (shouldClear) {
                      globalState.socket
                          ?.emitEvent(event: 'clear-expected-count', data: '');
                    }
                  }
                },
                iconSize: 80,
                icon: const Icon(Icons.bug_report),
              ),
              IconButton(
                onPressed: () {
                  final globalState = context.read<GlobalState>();
                  globalState.themeMode =
                      globalState.themeMode == ThemeMode.light
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
                    final globalState = context.read<GlobalState>();
                    await setVideo(globalState.socket!, true);
                    globalState.viewingRealtimeVideoFeed = true;
                    // ignore: use_build_context_synchronously
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (builderContext) =>
                            const RealTimeVideoStream(),
                      ),
                    );
                    // ignore: use_build_context_synchronously
                    await setVideo(globalState.socket!, false);
                    globalState.viewingRealtimeVideoFeed = false;
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
        ),
        Selector<GlobalState, PipelineState>(
          builder: (context, pipelineState, child) {
            if (pipelineState == PipelineState.running) {
              return const SizedBox.shrink();
            }

            return GestureDetector(
              onTap: () {
                context
                    .read<GlobalState>()
                    .socket
                    ?.emitEvent(event: 'play', data: 'play');
              },
              child: Material(
                color: Colors.black.withAlpha(150),
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        vertical: 50, horizontal: 20),
                    color: Theme.of(context).scaffoldBackgroundColor,
                    alignment: Alignment.center,
                    height: 600,
                    width: 600,
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          pipelineState.name.capitalize(),
                          style: const TextStyle(fontSize: 50),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 10),
                        const Text(
                          'Press button 3 to continue',
                          style: TextStyle(
                            fontStyle: FontStyle.italic,
                            fontSize: 30,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
          selector: (context, state) => state.currentPipelineState,
        ),
      ],
    );
  }
}
