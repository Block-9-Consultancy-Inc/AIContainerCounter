class LastEventCachedStream<T> {
  final Stream<T> _stream;
  T? lastEvent;

  Stream<T> get stream => _stream;

  LastEventCachedStream(Stream<T> stream)
      : _stream = stream.asBroadcastStream() {
    _stream.forEach((event) {
      lastEvent = event;
    });
  }
}