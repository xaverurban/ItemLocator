/// Fixing what the phone misread, without leaving the shelf.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_state.dart';
import '../data/models.dart';
import '../theme.dart' as palette;

/// Opens the editor for one product. Returns true if something was changed.
Future<bool> editProduct(
  BuildContext context,
  PlanogramPage page,
  Product product,
) async {
  final changed = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: palette.panel,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (context) => Padding(
      padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom),
      child: _EditProductSheet(page: page, product: product),
    ),
  );
  return changed ?? false;
}

class _EditProductSheet extends StatefulWidget {
  const _EditProductSheet({required this.page, required this.product});

  final PlanogramPage page;
  final Product product;

  @override
  State<_EditProductSheet> createState() => _EditProductSheetState();
}

class _EditProductSheetState extends State<_EditProductSheet> {
  late final TextEditingController _code =
      TextEditingController(text: widget.product.code);
  late final TextEditingController _name =
      TextEditingController(text: widget.product.name);
  late final TextEditingController _cases =
      TextEditingController(text: widget.product.cases?.toString() ?? '');
  bool _saving = false;

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _cases.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    final state = AppScope.of(context);
    final navigator = Navigator.of(context);
    final cases = int.tryParse(_cases.text.trim());
    await state.saveProductEdit(
      widget.page,
      widget.product,
      code: _code.text,
      name: _name.text,
      cases: cases,
      clearCases: _cases.text.trim().isEmpty,
    );
    navigator.pop(true);
  }

  Future<void> _delete() async {
    final state = AppScope.of(context);
    final navigator = Navigator.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: palette.panel,
        title: const Text('Remove this product?'),
        content: const Text(
            'Use this when the phone read something that is not a product at '
            'all. It only changes what is on this phone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Keep it')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Remove')),
        ],
      ),
    );
    if (confirmed != true) return;
    await state.deleteProduct(widget.page, widget.product);
    navigator.pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final product = widget.product;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(22, 14, 22, 22),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 42,
                height: 4,
                decoration: BoxDecoration(
                  color: palette.border,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 18),
            const Text('Fix this product',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(
              'Bay ${product.bay} · shelf ${product.shelf} · '
              'position ${product.positionLeft}'
              '${product.manuallyEdited ? ' · already checked' : ''}',
              style: const TextStyle(fontSize: 13, color: palette.textDim),
            ),
            const SizedBox(height: 18),
            TextField(
              controller: _code,
              keyboardType: const TextInputType.numberWithOptions(),
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              style: const TextStyle(
                  fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: 2),
              decoration: const InputDecoration(labelText: 'Code'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _name,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _cases,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                  labelText: 'Cases', hintText: 'leave empty if unknown'),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: Text(_saving ? 'Saving...' : 'Save'),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _saving ? null : _delete,
              icon: const Icon(Icons.delete_outline, size: 18),
              label: const Text('Not a product'),
              style: OutlinedButton.styleFrom(foregroundColor: palette.amber),
            ),
            const SizedBox(height: 8),
            const Text(
              'Corrections stay on this phone. Export the layout to send them '
              'to the desktop.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: palette.textFaint),
            ),
          ],
        ),
      ),
    );
  }
}
