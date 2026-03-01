import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:equatable/equatable.dart';

class Batch extends Equatable {
  final DateTime time;
  final Count actualCount;
  final Count? expectedCount;

  const Batch({
    required this.time,
    required this.actualCount,
    this.expectedCount,
  });

  @override
  List<Object?> get props => [
        time,
        actualCount,
        expectedCount,
      ];
}

class Count extends Equatable {
  final int count;
  final List<ClassWiseCount> classWiseCount;

  const Count({
    this.count = 0,
    this.classWiseCount = const [
      ClassWiseCount(class_: 'can', inCount: 0, outCount: 0),
      ClassWiseCount(class_: 'plastic', inCount: 0, outCount: 0),
      ClassWiseCount(class_: 'drinkbox', inCount: 0, outCount: 0),
      ClassWiseCount(class_: 'gabletop', inCount: 0, outCount: 0),
      ClassWiseCount(class_: 'pouch', inCount: 0, outCount: 0),
    ],
  });

  @override
  List<Object?> get props => [
        count,
        ...classWiseCount,
      ];
}
