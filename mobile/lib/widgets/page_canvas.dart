/// The page viewer: pinch to zoom, drag to pan, one product lit up.
library;

import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../data/models.dart';
import '../theme.dart' as palette;

class PageCanvas extends StatefulWidget {
  const PageCanvas({
    super.key,
    required this.page,
    this.product,
    this.onProductTapped,
    this.highlightColour = palette.highlight,
    this.dimLevel = 55,
  });

  final PlanogramPage page;
  final Product? product;
  final ValueChanged<Product>? onProductTapped;
  final Color highlightColour;
  final int dimLevel;

  @override
  State<PageCanvas> createState() => PageCanvasState();
}

class PageCanvasState extends State<PageCanvas>
    with SingleTickerProviderStateMixin {
  final TransformationController _controller = TransformationController();
  late final AnimationController _animation = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 260),
  );
  Animation<Matrix4>? _movement;
  Size _viewport = Size.zero;
  double _fit = 1;

  @override
  void initState() {
    super.initState();
    _animation.addListener(() {
      if (_movement != null) _controller.value = _movement!.value;
    });
  }

  @override
  void didUpdateWidget(PageCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.page.id != widget.page.id) {
      WidgetsBinding.instance.addPostFrameCallback((_) => fitPage());
    } else if (oldWidget.product?.code != widget.product?.code) {
      WidgetsBinding.instance.addPostFrameCallback((_) => zoomToProduct());
    }
  }

  @override
  void dispose() {
    _animation.dispose();
    _controller.dispose();
    super.dispose();
  }

  void _animateTo(Matrix4 target) {
    _movement = Matrix4Tween(begin: _controller.value, end: target).animate(
      CurvedAnimation(parent: _animation, curve: Curves.easeInOutCubic),
    );
    _animation.forward(from: 0);
  }

  void fitPage() {
    if (!mounted) return;
    _animateTo(Matrix4.identity());
  }

  /// Frame the product with a little of the shelf around it.
  void zoomToProduct() {
    final product = widget.product;
    final box = product?.bbox ?? product?.imageBbox;
    if (!mounted || box == null || _viewport.isEmpty || _fit <= 0) return;

    final width = box.w * _fit;
    final height = box.h * _fit;
    if (width <= 0 || height <= 0) return;

    // Show the label at a readable size without losing its surroundings.
    final scale = math.min(
      6.0,
      math.max(1.4, math.min(_viewport.width * 0.55 / width,
          _viewport.height * 0.35 / height)),
    );
    final centreX = box.centreX * _fit;
    final centreY = box.centreY * _fit;
    final target = Matrix4.identity()
      ..translate(_viewport.width / 2 - centreX * scale,
          _viewport.height / 2 - centreY * scale)
      ..scale(scale);
    _animateTo(target);
  }

  void _handleTap(TapUpDetails details) {
    if (widget.onProductTapped == null || _fit <= 0) return;
    final inverse = Matrix4.inverted(_controller.value);
    final scenePoint = MatrixUtils.transformPoint(
        inverse, details.localPosition);
    final pageX = scenePoint.dx / _fit;
    final pageY = scenePoint.dy / _fit;

    Product? best;
    var bestArea = double.infinity;
    for (final candidate in widget.page.products) {
      for (final box in [candidate.bbox, candidate.imageBbox]) {
        if (box == null) continue;
        if (box.contains(pageX, pageY) && box.w * box.h < bestArea) {
          best = candidate;
          bestArea = box.w * box.h;
        }
      }
    }
    if (best != null) widget.onProductTapped!(best);
  }

  @override
  Widget build(BuildContext context) {
    if (widget.page.imagePath.isEmpty ||
        widget.page.width <= 0 ||
        widget.page.height <= 0) {
      return const _MissingImage();
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final viewport = Size(constraints.maxWidth, constraints.maxHeight);
        final fit = math.min(viewport.width / widget.page.width,
            viewport.height / widget.page.height);
        if (viewport != _viewport || fit != _fit) {
          _viewport = viewport;
          _fit = fit;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (widget.product != null) {
              zoomToProduct();
            }
          });
        }

        return ClipRect(
          child: InteractiveViewer(
            transformationController: _controller,
            minScale: 0.9,
            maxScale: 12,
            boundaryMargin: const EdgeInsets.all(120),
            child: GestureDetector(
              onTapUp: _handleTap,
              child: SizedBox(
                width: viewport.width,
                height: viewport.height,
                child: Center(
                  child: SizedBox(
                    width: widget.page.width * fit,
                    height: widget.page.height * fit,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Image.file(
                          File(widget.page.imagePath),
                          fit: BoxFit.fill,
                          filterQuality: FilterQuality.medium,
                          errorBuilder: (_, __, ___) => const _MissingImage(),
                        ),
                        if (widget.product != null)
                          CustomPaint(
                            painter: _HighlightPainter(
                              page: widget.page,
                              product: widget.product!,
                              scale: fit,
                              colour: widget.highlightColour,
                              dim: widget.dimLevel,
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _MissingImage extends StatelessWidget {
  const _MissingImage();

  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'The picture of this page is not on the phone.\n'
            'Export the pack again from the desktop app.',
            textAlign: TextAlign.center,
            style: TextStyle(color: palette.textDim),
          ),
        ),
      );
}

class _HighlightPainter extends CustomPainter {
  _HighlightPainter({
    required this.page,
    required this.product,
    required this.scale,
    required this.colour,
    required this.dim,
  });

  final PlanogramPage page;
  final Product product;
  final double scale;
  final Color colour;
  final int dim;

  Rect _rect(BBox box, {double pad = 0}) => Rect.fromLTWH(
        (box.x - pad) * scale,
        (box.y - pad) * scale,
        (box.w + pad * 2) * scale,
        (box.h + pad * 2) * scale,
      );

  @override
  void paint(Canvas canvas, Size size) {
    final box = product.bbox ?? product.imageBbox;
    if (box == null) return;

    final pad = math.max(box.h * 0.10, 6.0);
    final target = _rect(box, pad: pad);
    final rounded = RRect.fromRectAndRadius(target, const Radius.circular(4));

    // Dim everything except the product.
    if (dim > 0) {
      final everything = Path()..addRect(Offset.zero & size);
      final hole = Path()..addRRect(rounded);
      canvas.drawPath(
        Path.combine(PathOperation.difference, everything, hole),
        Paint()..color = const Color(0xFF08090C).withValues(alpha: dim / 100),
      );
    }

    // The shelf run and the bay, faintly, for context.
    final bay = page.bayOf(product);
    final shelf = page.shelfOf(product);
    final context = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..color = colour.withValues(alpha: 0.45);
    if (bay != null && shelf != null) {
      canvas.drawRect(
        Rect.fromLTRB(bay.left * scale, shelf.top * scale, bay.right * scale,
            shelf.bottom * scale),
        context,
      );
    }
    if (bay != null) {
      canvas.drawRect(
        Rect.fromLTRB(bay.left * scale, 0, bay.right * scale, size.height),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.2
          ..color = palette.accent.withValues(alpha: 0.5),
      );
    }

    // The glow, then the outline.
    for (final (width, alpha) in [(11.0, 0.18), (7.0, 0.32), (4.0, 0.5)]) {
      canvas.drawRRect(
        rounded,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = width
          ..color = colour.withValues(alpha: alpha),
      );
    }
    canvas.drawRRect(
      rounded,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.4
        ..color = colour,
    );
  }

  @override
  bool shouldRepaint(_HighlightPainter old) =>
      old.product.code != product.code ||
      old.scale != scale ||
      old.colour != colour ||
      old.dim != dim;
}
