import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:equatable/equatable.dart';

class Batch extends Equatable {
  final int count;
  final DateTime time;
  final List<ClassWiseCount> classWiseCount;

  const Batch({
    required this.count,
    required this.time,
    required this.classWiseCount,
  });

  @override
  List<Object?> get props => [
    count,
    time,
    ...classWiseCount,
  ];
}
