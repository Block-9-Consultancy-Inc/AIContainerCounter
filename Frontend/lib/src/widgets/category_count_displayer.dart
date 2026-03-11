import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:flutter/material.dart';

class CategoryCountDisplayer extends StatelessWidget {
  final double scale;
  final double endPadding;
  final Count? count;
  const CategoryCountDisplayer({
    super.key,
    this.scale = 1.0,
    this.endPadding = 0,
    this.count,
  });

  @override
  Widget build(BuildContext context) {
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
                  'Can: ${count?.canCount ?? 0}${count?.canAccuracy == null ? '' : ' ${count!.canAccuracy!.toStringAsFixed(2)}%'}',
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
                  'Plastic: ${count?.plasticCount ?? 0}${count?.plasticAccuracy == null ? '' : ' ${count!.plasticAccuracy!.toStringAsFixed(2)}%'}',
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
                  'Gable Top: ${count?.gabletopCount ?? 0}${count?.gabletopAccuracy == null ? '' : ' ${count!.gabletopAccuracy!.toStringAsFixed(2)}%'}',
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
                  'Drink Box: ${count?.drinkboxCount ?? 0}${count?.drinkboxAccuracy == null ? '' : ' ${count!.drinkboxAccuracy!.toStringAsFixed(2)}%'}',
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
                  'Pouch: ${count?.pouchCount ?? 0}${count?.pouchAccuracy == null ? '' : ' ${count!.pouchAccuracy!.toStringAsFixed(2)}%'}',
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
