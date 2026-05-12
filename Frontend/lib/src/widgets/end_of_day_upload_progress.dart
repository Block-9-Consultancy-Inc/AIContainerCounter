import 'dart:math';

import 'package:flutter/material.dart';

class EndOfDayUploadProgress extends StatefulWidget {
  const EndOfDayUploadProgress({super.key});

  @override
  State<EndOfDayUploadProgress> createState() => _EndOfDayUploadProgressState();
}

class _EndOfDayUploadProgressState extends State<EndOfDayUploadProgress> {
  double metadataUploadProgress = 0;
  double s3UploadProgress = 0;
  double uploadToRoboflowProgress = 0;
  double videoCompressionProgress = 0;
  double videoS3UploadProgress = 0;

  @override
  void initState() {
    super.initState();

    mockActivity();
  }

  Future<void> mockActivity() async {
    final random = Random();
    const metadataUploadTime = 10;
    double metadataUploadCurrentTime = 0;
    while (metadataUploadProgress < 1) {
      final timeToWait = random.nextDouble();
      await Future.delayed(Duration(milliseconds: (timeToWait * 1000).toInt()));
      metadataUploadCurrentTime += timeToWait;
      if (!mounted) return;
      setState(() {
        metadataUploadProgress = metadataUploadCurrentTime / metadataUploadTime;
      });
    }

    const s3UploadTime = 100;
    double s3UploadCurrentTime = 0;
    while (s3UploadProgress < 1) {
      final timeToWait = random.nextDouble();
      await Future.delayed(Duration(milliseconds: (timeToWait * 1000).toInt()));
      s3UploadCurrentTime += timeToWait;
      if (!mounted) return;
      setState(() {
        s3UploadProgress = s3UploadCurrentTime / s3UploadTime;
      });
    }

    const roboflowUploadTime = 100;
    double roboflowUploadCurrentTime = 0;
    while (uploadToRoboflowProgress < 1) {
      final timeToWait = random.nextDouble();
      await Future.delayed(Duration(milliseconds: (timeToWait * 1000).toInt()));
      roboflowUploadCurrentTime += timeToWait;
      if (!mounted) return;
      setState(() {
        uploadToRoboflowProgress =
            roboflowUploadCurrentTime / roboflowUploadTime;
      });
    }

    const videoCompressionTime = 100;
    double videoCompressionCurrentTime = 0;
    while (videoCompressionProgress < 1) {
      final timeToWait = random.nextDouble();
      await Future.delayed(Duration(milliseconds: (timeToWait * 1000).toInt()));
      videoCompressionCurrentTime += timeToWait;
      if (!mounted) return;
      setState(() {
        videoCompressionProgress =
            videoCompressionCurrentTime / videoCompressionTime;
      });
    }

    const videoS3UploadTime = 100;
    double videoS3UploadCurrentTime = 0;
    while (videoS3UploadProgress < 1) {
      final timeToWait = random.nextDouble();
      await Future.delayed(Duration(milliseconds: (timeToWait * 1000).toInt()));
      videoS3UploadCurrentTime += timeToWait;
      if (!mounted) return;
      setState(() {
        videoS3UploadProgress = videoS3UploadTime / videoS3UploadCurrentTime;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Metadata Upload to CDC'),
        LinearProgressIndicator(
          value: metadataUploadProgress,
          minHeight: 10,
        ),
        const SizedBox(height: 10),
        const Text('Image Data Upload to S3'),
        LinearProgressIndicator(
          value: s3UploadProgress,
          minHeight: 10,
        ),
        const SizedBox(height: 10),
        const Text('Image Data Upload to Roboflow'),
        LinearProgressIndicator(
          value: uploadToRoboflowProgress,
          minHeight: 10,
        ),
        const SizedBox(height: 10),
        const Text('Video Compression'),
        LinearProgressIndicator(
          value: videoCompressionProgress,
          minHeight: 10,
        ),
        const SizedBox(height: 10),
        const Text('Video Data Upload to S3'),
        LinearProgressIndicator(
          value: videoS3UploadProgress,
          minHeight: 10,
        ),
        const SizedBox(height: 10),
      ],
    );
  }
}
