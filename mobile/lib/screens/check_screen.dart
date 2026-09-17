/// Everything on a layout that is worth a second look, worst first.
library;

import 'package:flutter/material.dart';

import '../data/editing.dart' as editing;
import '../data/models.dart';
import '../theme.dart' as palette;
import 'edit_product_sheet.dart';
import 'viewer_screen.dart';

class CheckScreen extends StatefulWidget {
  const CheckScreen({super.key, required this.layout});

  final Layout layout;

  @override
  State<CheckScreen> createState() => _CheckScreenState();
}

class _CheckScreenState extends State<CheckScreen> {
  @override
  Widget build(BuildContext context) {
    final pending = editing.productsToCheck(widget.layout);

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('To check',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            Text(widget.layout.title,
                style: const TextStyle(fontSize: 12, color: palette.textDim)),
          ],
        ),
      ),
      body: pending.isEmpty
          ? const _NothingToCheck()
          : ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
              itemCount: pending.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final (page, product) = pending[index];
                return _CheckTile(
                  page: page,
                  product: product,
                  layout: widget.layout,
                  onChanged: () => setState(() {}),
                );
              },
            ),
    );
  }
}

class _CheckTile extends StatelessWidget {
  const _CheckTile({
    required this.page,
    required this.product,
    required this.layout,
    required this.onChanged,
  });

  final PlanogramPage page;
  final Product product;
  final Layout layout;
  final VoidCallback onChanged;

  String get _why {
    final reasons = <String>[
      if (product.code.isEmpty) 'no code read',
      if (product.name.isEmpty) 'no name read',
      if (product.cases == null) 'no cases read',
      if (product.tags.contains('unreadable')) 'the label could not be read',
      if (product.confidence < 0.72) 'read at ${(product.confidence * 100).round()}%',
    ];
    return reasons.isEmpty ? 'needs a look' : reasons.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: palette.panel,
        borderRadius: BorderRadius.circular(palette.radius),
        border: Border.all(color: palette.amber.withValues(alpha: 0.4)),
      ),
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      product.code.isEmpty ? '(no code)' : product.code,
                      style: const TextStyle(
                          fontSize: 20, fontWeight: FontWeight.w700, letterSpacing: 1),
                    ),
                    Text(
                      product.name.isEmpty ? '(no name)' : product.name,
                      style: const TextStyle(fontSize: 14),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Page ${page.number} · bay ${product.bay} · '
                      'shelf ${product.shelf} · $_why',
                      style: const TextStyle(fontSize: 12, color: palette.amber),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => ViewerScreen(
                        page: page, layout: layout, product: product),
                  )),
                  icon: const Icon(Icons.image_search_outlined, size: 18),
                  label: const Text('See it'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton.icon(
                  onPressed: () async {
                    final changed = await editProduct(context, page, product);
                    if (changed) onChanged();
                  },
                  icon: const Icon(Icons.edit_outlined, size: 18),
                  label: const Text('Fix'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _NothingToCheck extends StatelessWidget {
  const _NothingToCheck();

  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 40),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.check_circle_outline, size: 46, color: palette.textFaint),
              SizedBox(height: 16),
              Text('Nothing to check',
                  style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
              SizedBox(height: 8),
              Text(
                'Everything on this layout was read clearly, or has been fixed '
                'already.',
                textAlign: TextAlign.center,
                style: TextStyle(color: palette.textDim, fontSize: 14, height: 1.45),
              ),
            ],
          ),
        ),
      );
}
