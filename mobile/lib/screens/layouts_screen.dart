/// What is on the phone: the layouts, their pages, and where they came from.
library;

import 'dart:io';

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../data/models.dart';
import '../theme.dart' as palette;
import 'viewer_screen.dart';

class LayoutsScreen extends StatelessWidget {
  const LayoutsScreen({super.key, required this.onImportRequested});

  final VoidCallback onImportRequested;

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);

    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
            child: Row(
              children: [
                const Expanded(
                  child: Text('Layouts',
                      style: TextStyle(
                          fontSize: 26, fontWeight: FontWeight.w800)),
                ),
                FilledButton.icon(
                  onPressed: onImportRequested,
                  icon: const Icon(Icons.add, size: 20),
                  label: const Text('Add sheets'),
                ),
              ],
            ),
          ),
          if (state.layouts.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Text(
                '${state.layouts.length} layout(s) · ${state.store.pageCount} '
                'page(s) · ${state.store.productCount} products',
                style: const TextStyle(color: palette.textDim, fontSize: 13),
              ),
            ),
          Expanded(
            child: state.layouts.isEmpty
                ? const _NoLayouts()
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
                    itemCount: state.layouts.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 12),
                    itemBuilder: (context, index) =>
                        _LayoutCard(layout: state.layouts[index]),
                  ),
          ),
        ],
      ),
    );
  }
}

class _LayoutCard extends StatelessWidget {
  const _LayoutCard({required this.layout});

  final Layout layout;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: palette.panel,
        borderRadius: BorderRadius.circular(palette.radius),
        border: Border.all(color: palette.border),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      layout.title.isEmpty ? 'Untitled layout' : layout.title,
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${layout.pages.length} page(s) · '
                      '${layout.productCount} products',
                      style: const TextStyle(
                          fontSize: 13, color: palette.textDim),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline, color: palette.textDim),
                tooltip: 'Remove this layout',
                onPressed: () => _confirmDelete(context),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 132,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: layout.pages.length,
              separatorBuilder: (_, __) => const SizedBox(width: 10),
              itemBuilder: (context, index) =>
                  _PageThumbnail(layout: layout, page: layout.pages[index]),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context) async {
    final state = AppScope.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: palette.panel,
        title: const Text('Remove this layout?'),
        content: Text(
          '${layout.title} and its ${layout.pages.length} page(s) will be '
          'deleted from this phone. The desktop copy is not touched.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep it'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed == true) await state.deleteLayout(layout.id);
  }
}

class _PageThumbnail extends StatelessWidget {
  const _PageThumbnail({required this.layout, required this.page});

  final Layout layout;
  final PlanogramPage page;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ViewerScreen(page: page, layout: layout),
      )),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 78,
            height: 104,
            decoration: BoxDecoration(
              color: palette.panelRaised,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: palette.border),
            ),
            clipBehavior: Clip.antiAlias,
            child: page.imagePath.isEmpty
                ? const Icon(Icons.image_not_supported_outlined,
                    color: palette.textFaint)
                : Image.file(File(page.imagePath), fit: BoxFit.cover),
          ),
          const SizedBox(height: 6),
          Text('Page ${page.number}',
              style: const TextStyle(fontSize: 12, color: palette.textDim)),
        ],
      ),
    );
  }
}

class _NoLayouts extends StatelessWidget {
  const _NoLayouts();

  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 40),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.layers_outlined, size: 46, color: palette.textFaint),
              SizedBox(height: 16),
              Text('Nothing imported yet',
                  style: TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
              SizedBox(height: 8),
              Text(
                'Photograph a sheet and it will be read here, or export a pack '
                'from the desktop app and import the .zip - that way is more '
                'accurate and much quicker.',
                textAlign: TextAlign.center,
                style: TextStyle(
                    color: palette.textDim, fontSize: 14, height: 1.45),
              ),
            ],
          ),
        ),
      );
}
