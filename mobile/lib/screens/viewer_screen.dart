/// Where the product is: the page, zoomed in on it, with the numbers underneath.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../data/locate.dart';
import '../data/models.dart';
import '../theme.dart' as palette;
import '../widgets/page_canvas.dart';
import '../widgets/result_card.dart';
import 'edit_product_sheet.dart';

class ViewerScreen extends StatefulWidget {
  const ViewerScreen({
    super.key,
    required this.page,
    required this.layout,
    this.product,
  });

  final PlanogramPage page;
  final Layout layout;
  final Product? product;

  @override
  State<ViewerScreen> createState() => _ViewerScreenState();
}

class _ViewerScreenState extends State<ViewerScreen> {
  final GlobalKey<PageCanvasState> _canvas = GlobalKey<PageCanvasState>();
  late PlanogramPage _page = widget.page;
  Product? _product;

  @override
  void initState() {
    super.initState();
    _product = widget.product;
  }

  void _showPage(PlanogramPage page) {
    setState(() {
      _page = page;
      _product = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final product = _product;
    final location =
        product == null ? null : locate(product, _page, widget.layout);
    final pages = widget.layout.pages;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              product?.code.isNotEmpty == true
                  ? product!.code
                  : widget.layout.title,
              style:
                  const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
            ),
            Text(
              'Page ${_page.number}'
              '${_page.totalPages != null ? ' of ${_page.totalPages}' : ''}'
              '  ·  ${_page.products.length} products',
              style: const TextStyle(fontSize: 12, color: palette.textDim),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Fit the page',
            onPressed: () => _canvas.currentState?.fitPage(),
            icon: const Icon(Icons.fit_screen_outlined),
          ),
          if (product != null)
            IconButton(
              tooltip: 'Back to the product',
              onPressed: () => _canvas.currentState?.zoomToProduct(),
              icon: const Icon(Icons.center_focus_strong_outlined),
            ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Stack(
              children: [
                Positioned.fill(
                  child: PageCanvas(
                    key: _canvas,
                    page: _page,
                    product: product,
                    highlightColour: state.highlight,
                    dimLevel: state.dimLevel,
                    onProductTapped: (tapped) =>
                        setState(() => _product = tapped),
                  ),
                ),
                if (pages.length > 1)
                  Positioned(
                    left: 12,
                    right: 12,
                    bottom: 12,
                    child: _PageStrip(
                      pages: pages,
                      current: _page,
                      onChosen: _showPage,
                    ),
                  ),
              ],
            ),
          ),
          if (location != null)
            _DetailsSheet(
              location: location,
              onEdit: () async {
                final changed = await editProduct(context, _page, product!);
                if (changed && mounted) setState(() {});
              },
            )
          else
            const _TapHint(),
        ],
      ),
    );
  }
}

class _DetailsSheet extends StatelessWidget {
  const _DetailsSheet({required this.location, required this.onEdit});

  final Location location;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: palette.background,
        border: Border(top: BorderSide(color: palette.border)),
      ),
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.46,
      ),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ResultCard(location: location),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: onEdit,
              icon: const Icon(Icons.edit_outlined, size: 18),
              label: Text(location.product.manuallyEdited
                  ? 'Edit this product'
                  : 'Something wrong? Fix it'),
            ),
          ],
        ),
      ),
    );
  }
}

class _TapHint extends StatelessWidget {
  const _TapHint();

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 20),
        decoration: const BoxDecoration(
          color: palette.background,
          border: Border(top: BorderSide(color: palette.border)),
        ),
        child: const Text(
          'Tap any product on the sheet to see where it goes.',
          textAlign: TextAlign.center,
          style: TextStyle(color: palette.textDim),
        ),
      );
}

class _PageStrip extends StatelessWidget {
  const _PageStrip({
    required this.pages,
    required this.current,
    required this.onChosen,
  });

  final List<PlanogramPage> pages;
  final PlanogramPage current;
  final ValueChanged<PlanogramPage> onChosen;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.bottomCenter,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
        decoration: BoxDecoration(
          color: palette.panel.withValues(alpha: 0.92),
          borderRadius: BorderRadius.circular(palette.radius),
          border: Border.all(color: palette.border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final page in pages)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 3),
                child: InkWell(
                  onTap: () => onChosen(page),
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(
                      color: page.id == current.id
                          ? palette.accent.withValues(alpha: 0.2)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      'Page ${page.number}',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: page.id == current.id
                            ? palette.accent
                            : palette.textDim,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
