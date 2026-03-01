import 'package:ai_container_counter/src/rust/api/simple.dart';

int getCategoryCount(List<ClassWiseCount>? classWiseCount, String category) {
  if (classWiseCount == null) return 0;
  return classWiseCount
      .firstWhere((e) => e.class_ == category,
          orElse: () =>
              ClassWiseCount(class_: category, inCount: 0, outCount: 0))
      .inCount;
}
