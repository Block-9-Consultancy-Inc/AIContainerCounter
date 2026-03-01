import 'dart:io';

import 'package:ai_container_counter/src/models/batch.dart';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:http/http.dart' as http;
import 'dart:convert' show json;

Future<void> printReceipt(
    int transactionNumber,
    Batch submittedBatch) async {
  final categories = submittedBatch.actualCount.classWiseCount.asMap().map(
      (index, classWiseCount) =>
          MapEntry(classWiseCount.class_, classWiseCount.outCount));

  final response = await http.post(
    Uri.parse('http://localhost:3000/print-receipt'),
    headers: {'Content-Type': 'application/json'},
    body: json.encode({
      'transactionNumber': transactionNumber,
      'totalCount': submittedBatch.actualCount.count,
      'categories': categories,
    }),
  );

  if (response.statusCode >= 400) {
    throw HttpException('${response.statusCode}: ${response.body}');
  }
}

Future<void> setVideo(Socket socket, bool on) async {
  await socket.emitEvent(event: 'set-video', data: on.toString());
}
