import 'package:ai_container_counter/src/models/global_state.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class RealTimeVideoStream extends StatelessWidget {
  const RealTimeVideoStream({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        backgroundColor: Colors.black.withAlpha(0),
        title: Row(
          children: [
            IconButton(
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.close),
              color: const Color.fromRGBO(56, 182, 255, 1),
            ),
            const SizedBox(width: 10),
            ElevatedButton(
                onPressed: context.read<GlobalState>().submitBatch,
                child: const Text('Submit Batch')),
          ],
        ),
      ),
      extendBodyBehindAppBar: true,
      body: Center(
        child: AspectRatio(
          aspectRatio: 1920 / 1080,
          child: Texture(
            textureId: context.read<GlobalState>().textureId!,
            filterQuality: FilterQuality.medium,
          ),
        ),
      ),
    );
  }
}
