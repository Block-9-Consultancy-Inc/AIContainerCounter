import 'package:ai_container_counter/src/rust/models/multi_container_image.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

class RenderedBBox {
  final BBox bbox;

  final double x1;
  final double y1;
  final double x2;
  final double y2;

  const RenderedBBox({
    required this.bbox,
    required this.x1,
    required this.y1,
    required this.x2,
    required this.y2,
  });

  RenderedBBox.fromBBox(this.bbox)
      : x1 = bbox.x1.toDouble(),
        y1 = bbox.y1.toDouble(),
        x2 = bbox.x2.toDouble(),
        y2 = bbox.y2.toDouble();

  RenderedBBox copyWith({
    BBox? bbox,
    double? x1,
    double? y1,
    double? x2,
    double? y2,
  }) {
    return RenderedBBox(
      bbox: bbox ?? this.bbox,
      x1: x1 ?? this.x1,
      y1: y1 ?? this.y1,
      x2: x2 ?? this.x2,
      y2: y2 ?? this.y2,
    );
  }
}

class MultiContainerImageViewerParams {
  Size? renderedImageSize;
  late Size prevRenderedImageSize;
  final MultiContainerImage multiContainerImage;
  late List<RenderedBBox> bboxes;

  MultiContainerImageViewerParams({
    required this.multiContainerImage,
    this.renderedImageSize,
  }) {
    prevRenderedImageSize = Size(multiContainerImage.width.toDouble(),
        multiContainerImage.height.toDouble());
    bboxes = multiContainerImage.bboxes
        .map((e) => RenderedBBox.fromBBox(e))
        .toList();
  }

  void reactToFrameUpdates(Size? size, BuildContext context) {
    prevRenderedImageSize = renderedImageSize ?? prevRenderedImageSize;
    renderedImageSize = size;
    bboxes = bboxes
        .map(
          (e) => e.copyWith(
            x1: e.x1 * (renderedImageSize!.width / prevRenderedImageSize.width),
            y1: e.y1 *
                (renderedImageSize!.height / prevRenderedImageSize.height),
            x2: e.x2 * (renderedImageSize!.width / prevRenderedImageSize.width),
            y2: e.y2 *
                (renderedImageSize!.height / prevRenderedImageSize.height),
          ),
        )
        .toList();
  }
}

class MultiContainerImageViewer extends StatefulWidget {
  final String batchId;
  final Map<int, String> predictedCategories;
  final MultiContainerImageViewerParams params;
  const MultiContainerImageViewer({
    super.key,
    required this.batchId,
    required this.predictedCategories,
    required this.params,
  });

  @override
  State<MultiContainerImageViewer> createState() =>
      _MultiContainerImageViewerState();
}

class _MultiContainerImageViewerState extends State<MultiContainerImageViewer>
    with WidgetsBindingObserver {
  final imageKey = GlobalKey();

  Size? currentWindowSize;
  Size? prevWindowSize;

  late MultiContainerImageViewerParams params;

  RenderedBBox? focusedBBox;

  @override
  void initState() {
    super.initState();

    params = widget.params;
    setState(() {});
  }

  Future<void> reactToFrameUpdates() async {
    // ignore: avoid_print
    print('reacting to frame updates');
    Size? size = imageKey.currentContext?.size;
    while (size == null || size == const Size(0, 0)) {
      await Future.delayed(const Duration(milliseconds: 50));
      size = imageKey.currentContext?.size;
    }
    if (mounted) {
      params.reactToFrameUpdates(size, context);
    }
    setState(() {});
  }

  void updateFrameSize(Duration _) {
    reactToFrameUpdates();
  }

  @override
  Widget build(BuildContext context) {
    prevWindowSize = currentWindowSize;
    currentWindowSize = MediaQuery.of(context).size;

    if (prevWindowSize != currentWindowSize) {
      WidgetsBinding.instance.addPostFrameCallback(updateFrameSize);
    }

    return CachedNetworkImage(
      key: Key(params.multiContainerImage.id),
      imageUrl:
          'http://localhost:5000/images/${widget.batchId}/multi_container_images/${params.multiContainerImage.id}.${params.multiContainerImage.index}.jpg',
      imageBuilder: (context, imageProvider) => Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          Image(key: imageKey, image: imageProvider),
          if (params.renderedImageSize != null && params.bboxes.isNotEmpty)
            ...params.bboxes.map(
              (bbox) => Positioned(
                left: bbox.x1,
                top: bbox.y1,
                child: InkWell(
                  onHover: (isHovering) {
                    setState(() {
                      focusedBBox = isHovering ? bbox : null;
                    });
                  },
                  onTap: () {},
                  child: Container(
                    width: bbox.x2 - bbox.x1,
                    height: bbox.y2 - bbox.y1,
                    decoration: BoxDecoration(
                        border: Border.all(
                      color: Colors.red,
                      width: 2,
                    )),
                  ),
                ),
              ),
            ),
          if (focusedBBox != null && params.renderedImageSize != null) ...[
            Positioned.fill(
              child: IgnorePointer(
                key: Key(focusedBBox!.bbox.id),
                child: ClipPath(
                  clipper: InvertedClipper(focusedBBox!),
                  child: Container(
                    color: Colors.black54,
                  ),
                ),
              ),
            ),
            Positioned(
              top: focusedBBox!.y1 - 20,
              left: focusedBBox!.x1,
              child: Text(
                  '${focusedBBox!.bbox.trackerId}: ${widget.predictedCategories[focusedBBox!.bbox.trackerId] ?? 'no detected category'}'),
            ),
          ]
        ],
      ),
    );
  }
}

class InvertedClipper extends CustomClipper<Path> {
  RenderedBBox bbox;

  InvertedClipper(this.bbox);

  @override
  Path getClip(Size size) {
    return Path()
      ..addRect(Rect.fromLTRB(bbox.x1, bbox.y1, bbox.x2, bbox.y2))
      ..addRect(Rect.fromLTWH(0.0, 0.0, size.width, size.height))
      ..fillType = PathFillType.evenOdd;
  }

  @override
  bool shouldReclip(CustomClipper<Path> oldClipper) => false;
}
