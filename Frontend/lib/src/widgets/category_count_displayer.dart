import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:ai_container_counter/src/utils/calculation_utils.dart';
import 'package:ai_container_counter/src/utils/class_wise_count_utils.dart';
import 'package:flutter/material.dart';

class CategoryCountDisplayer extends StatelessWidget {
  final double scale;
  final double endPadding;
  final List<ClassWiseCount> classWiseCount;
  final List<ClassWiseCount>? expectedClassWiseCount;
  const CategoryCountDisplayer({
    super.key,
    this.scale = 1.0,
    this.endPadding = 0,
    this.classWiseCount = const [],
    this.expectedClassWiseCount,
  });

  @override
  Widget build(BuildContext context) {
    final can = getCategoryCount(classWiseCount, 'can');
    final canExpected = getCategoryCount(expectedClassWiseCount, 'can');
    final plastic = getCategoryCount(classWiseCount, 'plastic');
    final plasticExpected = getCategoryCount(expectedClassWiseCount, 'plastic');
    final gableTop = getCategoryCount(classWiseCount, 'gabletop');
    final gableTopExpected =
        getCategoryCount(expectedClassWiseCount, 'gabletop');
    final drinkBox = getCategoryCount(classWiseCount, 'drinkbox');
    final drinkBoxExpected =
        getCategoryCount(expectedClassWiseCount, 'drinkbox');
    final pouch = getCategoryCount(classWiseCount, 'pouch');
    final pouchExpected = getCategoryCount(expectedClassWiseCount, 'pouch');
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
                  'Can: $can${expectedClassWiseCount == null ? '' : ' ${computeCountAccuracy(can, canExpected)}'}',
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
                  'Plastic: $plastic${expectedClassWiseCount == null ? '' : ' ${computeCountAccuracy(plastic, plasticExpected)}'}',
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
                  'Gable Top: $gableTop${expectedClassWiseCount == null ? '' : ' ${computeCountAccuracy(gableTop, gableTopExpected)}'}',
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
                  'Drink Box: $drinkBox${expectedClassWiseCount == null ? '' : ' ${computeCountAccuracy(drinkBox, drinkBoxExpected)}'}',
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
                  'Pouch: $pouch${expectedClassWiseCount == null ? '' : ' ${computeCountAccuracy(pouch, pouchExpected)}'}',
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
