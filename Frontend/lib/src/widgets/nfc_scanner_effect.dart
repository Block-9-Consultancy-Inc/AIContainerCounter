import 'package:flutter/material.dart';
import 'dart:math' as math;

class NFCScannerEffect extends StatefulWidget {
  final Widget nfcTagWidget;
  final double scannerSize;
  final Color primaryColor;
  final Color secondaryColor;
  final Duration animationDuration;
  final Duration pulseInterval;

  const NFCScannerEffect({
    super.key,
    required this.nfcTagWidget,
    this.scannerSize = 250,
    this.primaryColor = Colors.blue,
    this.secondaryColor = Colors.lightBlue,
    this.animationDuration = const Duration(milliseconds: 1500),
    this.pulseInterval = const Duration(milliseconds: 2000),
  });

  @override
  State<NFCScannerEffect> createState() => _NFCScannerEffectState();
}

class _NFCScannerEffectState extends State<NFCScannerEffect>
    with TickerProviderStateMixin {
  late AnimationController _pulseController;
  late AnimationController _rotationController;
  late AnimationController _waveController;

  late Animation<double> _pulseAnimation;
  late Animation<double> _rotationAnimation;
  late Animation<double> _waveAnimation;

  @override
  void initState() {
    super.initState();

    // Pulse animation for the outer rings
    _pulseController = AnimationController(
      duration: widget.animationDuration,
      vsync: this,
    );
    _pulseAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _pulseController,
      curve: Curves.easeOut,
    ));

    // Rotation animation for the scanning arc
    _rotationController = AnimationController(
      duration: const Duration(seconds: 3),
      vsync: this,
    );
    _rotationAnimation = Tween<double>(
      begin: 0.0,
      end: 2 * math.pi,
    ).animate(CurvedAnimation(
      parent: _rotationController,
      curve: Curves.linear,
    ));

    // Wave animation for ripple effect
    _waveController = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    );
    _waveAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _waveController,
      curve: Curves.easeOut,
    ));

    // Start animations
    _rotationController.repeat();
    _startPulseSequence();
  }

  void _startPulseSequence() async {
    while (mounted) {
      await Future.delayed(widget.pulseInterval);
      if (mounted) {
        _pulseController.forward().then((_) {
          _pulseController.reset();
        });
        _waveController.forward().then((_) {
          _waveController.reset();
        });
      }
    }
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _rotationController.dispose();
    _waveController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: widget.scannerSize,
      height: widget.scannerSize,
      alignment: Alignment.center,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Background circles
          Center(
            child: Container(
              width: widget.scannerSize,
              height: widget.scannerSize,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: widget.primaryColor.withAlpha(85),
                  width: 2,
                ),
              ),
            ),
          ),

          // Animated pulse rings
          AnimatedBuilder(
            animation: _pulseAnimation,
            builder: (context, child) {
              return Center(
                child: Container(
                  width: widget.scannerSize * 0.8 * _pulseAnimation.value,
                  height: widget.scannerSize * 0.8 * _pulseAnimation.value,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: widget.primaryColor.withAlpha(
                          (0.8 * (255 - 255 * _pulseAnimation.value)).toInt()),
                      width: 3,
                    ),
                  ),
                ),
              );
            },
          ),

          // Wave ripple effect
          AnimatedBuilder(
            animation: _waveAnimation,
            builder: (context, child) {
              return Center(
                child: Container(
                  width: widget.scannerSize * 0.6 * _waveAnimation.value,
                  height: widget.scannerSize * 0.6 * _waveAnimation.value,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: widget.secondaryColor.withAlpha(
                          (0.6 * (255 - 255 * _waveAnimation.value)).toInt()),
                      width: 2,
                    ),
                  ),
                ),
              );
            },
          ),

          // Rotating scanner arc
          AnimatedBuilder(
            animation: _rotationAnimation,
            builder: (context, child) {
              return Center(
                child: CustomPaint(
                  size: Size(widget.scannerSize, widget.scannerSize),
                  painter: NFCScannerPainter(
                    rotation: _rotationAnimation.value,
                    color: widget.primaryColor,
                  ),
                ),
              );
            },
          ),

          // NFC Tag in center
          Center(child: widget.nfcTagWidget),

          // NFC Icon overlay
          Center(
            child: Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(
                color: widget.primaryColor.withAlpha((0.1 * 255).toInt()),
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.nfc,
                color: widget.primaryColor,
                size: widget.scannerSize * 0.1,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class NFCScannerPainter extends CustomPainter {
  final double rotation;
  final Color color;

  NFCScannerPainter({required this.rotation, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 4
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width * 0.3;

    // Draw scanning arc
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      rotation,
      math.pi / 3, // 60 degrees
      false,
      paint,
    );

    // Draw gradient effect on the arc
    final gradientPaint = Paint()
      ..shader = LinearGradient(
        colors: [
          color.withAlpha((0.2 * 255).toInt()),
          color,
          color.withAlpha((0.2 * 255).toInt()),
        ],
      ).createShader(Rect.fromCircle(center: center, radius: radius))
      ..strokeWidth = 6
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      rotation,
      math.pi / 4, // 45 degrees
      false,
      gradientPaint,
    );
  }

  @override
  bool shouldRepaint(covariant NFCScannerPainter oldDelegate) {
    return oldDelegate.rotation != rotation;
  }
}

// Example usage
class EazyPickupNFCScanner extends StatelessWidget {
  const EazyPickupNFCScanner({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      return Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          NFCScannerEffect(
            nfcTagWidget: Container(
              width: constraints.maxHeight * 0.25,
              height: constraints.maxHeight * 0.25,
              decoration: BoxDecoration(
                color: Colors.grey[800],
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.grey[600]!, width: 2),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.credit_card,
                    color: Colors.white,
                    size: constraints.maxHeight * 0.1,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'NFC',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: constraints.maxHeight * 0.05,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
            scannerSize: constraints.maxHeight * 0.75,
            primaryColor: Colors.blue,
            secondaryColor: Colors.lightBlue,
          ),
          SizedBox(height: constraints.maxHeight * 0.05),
          const Text(
            'SCAN EAZY PICKUP BAG NFC',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
            ),
          ),
        ],
      );
    });
  }
}
