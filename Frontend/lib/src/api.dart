import 'dart:io';
import 'package:ai_container_counter/src/rust/api/simple.dart';
import 'package:http/http.dart' as http;
import 'dart:convert' show json;

Future<void> printReceipt(
    int transactionNumber,
    Batch submittedBatch) async {

  final response = await http.post(
    Uri.parse('http://localhost:3000/print-receipt'),
    headers: {'Content-Type': 'application/json'},
    body: json.encode({
      'transactionNumber': transactionNumber,
      'totalCount': submittedBatch.count.count.toInt(),
      'categories': {
        'can': submittedBatch.count.canCount.toInt(),
        'plastic': submittedBatch.count.plasticCount.toInt(),
        'drinkbox': submittedBatch.count.drinkboxCount.toInt(),
        'gabletop': submittedBatch.count.gabletopCount.toInt(),
        'pouch': submittedBatch.count.pouchCount.toInt(),
      },
    }),
  );

  if (response.statusCode >= 400) {
    throw HttpException('${response.statusCode}: ${response.body}');
  }
}

Future<void> setVideo(Socket socket, bool on) async {
  await socket.emitEvent(event: 'set-video', data: on.toString());
}
