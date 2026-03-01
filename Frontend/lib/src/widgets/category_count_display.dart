import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:flutter/material.dart';

class CategoryCountDisplay extends StatelessWidget {
  final double scale;
  final double endPadding;
  final List<ClassWiseCount> classWiseCount;
  const CategoryCountDisplay({
    super.key,
    this.scale = 1.0,
    this.endPadding = 0,
    this.classWiseCount = const [],
  });

  @override
  Widget build(BuildContext context) {
    final aluminum = classWiseCount
        .firstWhere((e) => e.class_ == 'can',
            orElse: () =>
                const ClassWiseCount(class_: 'can', inCount: 0, outCount: 0))
        .inCount;
    final plastic = classWiseCount
        .firstWhere((e) => e.class_ == 'plastic',
            orElse: () => const ClassWiseCount(
                class_: 'plastic', inCount: 0, outCount: 0))
        .inCount;
    final gableTop = classWiseCount
        .firstWhere((e) => e.class_ == 'gabletop',
            orElse: () => const ClassWiseCount(
                class_: 'gabletop', inCount: 0, outCount: 0))
        .inCount;
    final drinkBox = classWiseCount
        .firstWhere((e) => e.class_ == 'drinkbox',
            orElse: () => const ClassWiseCount(
                class_: 'drinkbox', inCount: 0, outCount: 0))
        .inCount;
    final pouch = classWiseCount
        .firstWhere((e) => e.class_ == 'pouch',
            orElse: () =>
                const ClassWiseCount(class_: 'pouch', inCount: 0, outCount: 0))
        .inCount;
    return Expanded(
        child: Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Aluminum: $aluminum',
                  style: TextStyle(
                    fontSize: 20 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Plastic: $plastic',
                  style: TextStyle(
                    fontSize: 20 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Gable Top: $gableTop',
                  style: TextStyle(
                    fontSize: 20 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Drink Box: $drinkBox',
                  style: TextStyle(
                    fontSize: 20 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(12.5 * scale),
                child: Text(
                  'Pouch: $pouch',
                  style: TextStyle(
                    fontSize: 20 * scale,
                    height: 0.75 * scale,
                    color:
                        Theme.of(context).colorScheme.primary.withOpacity(0.8),
                  ),
                ),
              ),
            ],
          ),
        ),
        SizedBox(width: endPadding)
      ],
    ));
  }
}