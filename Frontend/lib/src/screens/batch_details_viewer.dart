// ignore_for_file: avoid_print, use_build_context_synchronously

import 'dart:math' as math;

import 'package:ai_container_counter/src/rust/api/models/count.dart';
import 'package:ai_container_counter/src/widgets/multi_container_image_viewer.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class BatchDetailsViewer extends StatefulWidget {
  final Batch batch;
  const BatchDetailsViewer({
    super.key,
    required this.batch,
  });

  @override
  State<BatchDetailsViewer> createState() => _BatchDetailsViewerState();
}

class _BatchDetailsViewerState extends State<BatchDetailsViewer> {
  late final List<MultiContainerImageViewerParams> parameters;
  final pageController = PageController();
  final focusNode = FocusNode();
  int currentIndex = 0;

  @override
  void initState() {
    super.initState();
    parameters = widget.batch.multiContainerImages
        .map((e) => MultiContainerImageViewerParams(multiContainerImage: e))
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    return KeyboardListener(
      autofocus: true,
      focusNode: focusNode,
      onKeyEvent: (keyEvent) {
        if ((keyEvent is KeyDownEvent || keyEvent is KeyRepeatEvent) &&
            keyEvent.logicalKey == LogicalKeyboardKey.arrowLeft) {
          setState(() {
            currentIndex = math.max(currentIndex - 1, 0);
          });
        }
        if ((keyEvent is KeyDownEvent || keyEvent is KeyRepeatEvent) &&
            keyEvent.logicalKey == LogicalKeyboardKey.arrowRight) {
          setState(() {
            currentIndex = math.min(currentIndex + 1, parameters.length - 1);
          });
        }
        pageController.jumpToPage(currentIndex);
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Single Container Image Result'),
          backgroundColor: Theme.of(context)
              .primaryColorDark
              .withAlpha((0.45 * 255).toInt()),
        ),
        body: Stack(
          alignment: Alignment.center,
          children: [
            PageView.builder(
              physics: const NeverScrollableScrollPhysics(),
              allowImplicitScrolling: false,
              controller: pageController,
              itemCount: parameters.length,
              itemBuilder: (context, index) {
                return InteractiveViewer(
                  maxScale: 10,
                  child: Center(
                    child: MultiContainerImageViewer(
                      batchId: widget.batch.id,
                      params: parameters[index],
                      predictedCategories: widget.batch.predictedCategories,
                    ),
                  ),
                );
              },
            ),
            Positioned(
              left: 0,
              child: IconButton(
                onPressed: () {
                  setState(() {
                    currentIndex = math.max(currentIndex - 1, 0);
                  });
                  pageController.jumpToPage(currentIndex);
                },
                icon: const Icon(Icons.arrow_back),
              ),
            ),
            Positioned(
              right: 0,
              child: IconButton(
                onPressed: () {
                  setState(() {
                    currentIndex =
                        math.min(currentIndex + 1, parameters.length - 1);
                  });
                  pageController.jumpToPage(currentIndex);
                },
                icon: const Icon(Icons.arrow_forward),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
