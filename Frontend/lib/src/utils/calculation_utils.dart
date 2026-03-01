String computeCountAccuracy(int actual, int expected) {
  if (expected == 0) return '0.0%';
  return '${((1.0 - ((actual - expected).abs() / expected)) * 100.0).toStringAsFixed(2)}%';
}
