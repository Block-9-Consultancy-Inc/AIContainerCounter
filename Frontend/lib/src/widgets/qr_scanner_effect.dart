import 'package:flutter/material.dart';

class QRScannerEffect extends StatefulWidget {
  final Widget qrCodeWidget;
  final double scannerSize;
  final Color scanLineColor;
  final double scanLineHeight;
  final Duration animationDuration;
  final bool animate;

  const QRScannerEffect({
    super.key,
    required this.qrCodeWidget,
    this.scannerSize = 250,
    this.scanLineColor = Colors.red,
    this.scanLineHeight = 2,
    this.animationDuration = const Duration(seconds: 2),
    this.animate = false,
  });

  @override
  State<QRScannerEffect> createState() => _QRScannerEffectState();
}

class _QRScannerEffectState extends State<QRScannerEffect>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();

    if (!widget.animate) return;
    _animationController = AnimationController(
      duration: widget.animationDuration,
      vsync: this,
    );

    _animation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    ));

    _animationController.repeat(reverse: true);
  }

  @override
  void dispose() {
    if (widget.animate) {
      _animationController.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      alignment: Alignment.center,
      width: widget.scannerSize,
      height: widget.scannerSize,
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          // QR Code
          widget.qrCodeWidget,

          // Scanner overlay with corners
          CustomPaint(
            size: Size(widget.scannerSize, widget.scannerSize),
            painter: ScannerOverlayPainter(),
          ),

          // Animated scan line
          if (widget.animate)
            AnimatedBuilder(
              animation: _animation,
              builder: (context, child) => Positioned(
                top: _animation.value *
                    (widget.scannerSize - widget.scanLineHeight),
                left: 20,
                right: 20,
                child: Container(
                  height: widget.scanLineHeight,
                  decoration: BoxDecoration(
                    color: widget.scanLineColor,
                    boxShadow: [
                      BoxShadow(
                        color: widget.scanLineColor.withAlpha(128),
                        blurRadius: 4,
                        spreadRadius: 1,
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class ScannerOverlayPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;

    const cornerLength = 20.0;
    const cornerOffset = 10.0;

    // Top-left corner
    canvas.drawPath(
      Path()
        ..moveTo(cornerOffset, cornerOffset + cornerLength)
        ..lineTo(cornerOffset, cornerOffset)
        ..lineTo(cornerOffset + cornerLength, cornerOffset),
      paint,
    );

    // Top-right corner
    canvas.drawPath(
      Path()
        ..moveTo(size.width - cornerOffset - cornerLength, cornerOffset)
        ..lineTo(size.width - cornerOffset, cornerOffset)
        ..lineTo(size.width - cornerOffset, cornerOffset + cornerLength),
      paint,
    );

    // Bottom-left corner
    canvas.drawPath(
      Path()
        ..moveTo(cornerOffset, size.height - cornerOffset - cornerLength)
        ..lineTo(cornerOffset, size.height - cornerOffset)
        ..lineTo(cornerOffset + cornerLength, size.height - cornerOffset),
      paint,
    );

    // Bottom-right corner
    canvas.drawPath(
      Path()
        ..moveTo(size.width - cornerOffset - cornerLength,
            size.height - cornerOffset)
        ..lineTo(size.width - cornerOffset, size.height - cornerOffset)
        ..lineTo(size.width - cornerOffset,
            size.height - cornerOffset - cornerLength),
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class ExpressQRCode extends StatelessWidget {
  const ExpressQRCode({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      return QRScannerEffect(
        animate: true,
        qrCodeWidget: Container(
          width: constraints.maxHeight * 0.7,
          height: constraints.maxHeight * 0.7,
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Center(
            child: Text(
              'SCAN EXPRESS\nQR CODE',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
                color: Colors.black,
              ),
            ),
          ),
        ),
        scannerSize: constraints.maxHeight * 0.9,
        scanLineColor: Colors.red,
        animationDuration: const Duration(seconds: 2),
      );
    });
  }
}

class ScanAuthorizedUserQRCode extends StatelessWidget {
  const ScanAuthorizedUserQRCode({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      return QRScannerEffect(
        animate: false,
        qrCodeWidget: Container(
          width: constraints.maxHeight * 0.7,
          height: constraints.maxHeight * 0.7,
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Center(
            child: Text(
              'SCAN AUTHORIZED ID\nQR CODE TO START',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Colors.black,
              ),
            ),
          ),
        ),
        scannerSize: constraints.maxHeight * 0.9,
        scanLineColor: Colors.red,
        animationDuration: const Duration(seconds: 2),
      );
    });
  }
}

class UnauthorizedUserQRCode extends StatelessWidget {
  const UnauthorizedUserQRCode({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      return QRScannerEffect(
        animate: false,
        qrCodeWidget: Container(
          width: constraints.maxHeight * 0.7,
          height: constraints.maxHeight * 0.7,
          decoration: BoxDecoration(
            color: Colors.red,
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Center(
            child: Text(
              'USER NOT\nAUTHORIZED',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
          ),
        ),
        scannerSize: constraints.maxHeight * 0.9,
        scanLineColor: Colors.red,
        animationDuration: const Duration(seconds: 2),
      );
    });
  }
}
