import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

class AnimatedLogo extends StatefulWidget {
  const AnimatedLogo({super.key, required this.size});

  final double size;

  @override
  State<AnimatedLogo> createState() => _AnimatedLogoState();
}

class _AnimatedLogoState extends State<AnimatedLogo>
    with SingleTickerProviderStateMixin {
  late final AnimationController controller;

  @override
  void initState() {
    super.initState();
    controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..repeat();
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          return CustomPaint(
            painter: VisionSafeLogoPainter(controller.value),
          );
        },
      ),
    );
  }
}

class VisionSafeLogoPainter extends CustomPainter {
  const VisionSafeLogoPainter(this.progress);

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final scale = size.shortestSide / 200;
    canvas.scale(scale);

    final center = const Offset(100, 100);
    final outerRing = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 3
      ..color = AppColors.orange;

    canvas.save();
    canvas.translate(100, 100);
    canvas.rotate(progress * math.pi * 2);
    canvas.translate(-100, -100);
    for (var i = 0; i < 4; i++) {
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: 90),
        i * math.pi / 2,
        math.pi / 2 - .42,
        false,
        outerRing,
      );
    }
    canvas.restore();

    final innerRing = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 1.6
      ..color = AppColors.orange.withOpacity(.62);
    canvas.save();
    canvas.translate(100, 100);
    canvas.rotate(-progress * math.pi * 2 * 1.4);
    canvas.translate(-100, -100);
    for (var i = 0; i < 8; i++) {
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: 78),
        i * math.pi / 4,
        math.pi / 4 - .34,
        false,
        innerRing,
      );
    }
    canvas.restore();

    final shieldStroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 3
      ..color = AppColors.orange;

    final shield = Path()
      ..moveTo(100, 35)
      ..lineTo(145, 55)
      ..lineTo(145, 95)
      ..cubicTo(145, 125, 125, 150, 100, 165)
      ..cubicTo(75, 150, 55, 125, 55, 95)
      ..lineTo(55, 55)
      ..close();
    canvas.drawPath(
      shield,
      Paint()
        ..color = const Color(0xFF0A0A0A)
        ..style = PaintingStyle.fill,
    );
    canvas.drawPath(shield, shieldStroke);

    final eye = Path()
      ..moveTo(70, 100)
      ..cubicTo(82, 86, 91, 85, 100, 85)
      ..cubicTo(109, 85, 118, 86, 130, 100)
      ..cubicTo(118, 114, 109, 115, 100, 115)
      ..cubicTo(91, 115, 82, 114, 70, 100);
    canvas.drawPath(eye, shieldStroke..strokeWidth = 2);

    final pulse = .5 + .5 * math.sin(progress * math.pi * 4);
    canvas.drawCircle(
      center,
      10 + pulse * 4,
      Paint()..color = AppColors.orange.withOpacity(.18 + pulse * .22),
    );
    canvas.drawCircle(center, 6 + pulse, Paint()..color = AppColors.lightOrange);

    final detail = Paint()
      ..color = AppColors.orange
      ..strokeWidth = 1;
    canvas.drawLine(const Offset(100, 35), const Offset(100, 45), detail);
    canvas.drawLine(const Offset(100, 155), const Offset(100, 165), detail);
  }

  @override
  bool shouldRepaint(covariant VisionSafeLogoPainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
