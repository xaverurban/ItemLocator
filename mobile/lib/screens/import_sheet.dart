/// Bringing sheets in: photograph them here, or take what the desktop prepared.
library;

import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../app_state.dart';
import '../data/library_store.dart';
import '../data/photo_import.dart';
import '../theme.dart' as palette;

enum ImportChoice { camera, gallery, pack }

/// Asks how the sheets are arriving.
Future<ImportChoice?> askHowToImport(BuildContext context) {
  return showModalBottomSheet<ImportChoice>(
    context: context,
    backgroundColor: palette.panel,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    // Scrollable so the options still fit on a short screen, or with the
    // system font size turned up.
    builder: (context) => SafeArea(
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 12),
            Container(
              width: 42,
              height: 4,
              decoration: BoxDecoration(
                color: palette.border,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 18),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 22),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('Add layout sheets',
                    style:
                        TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
              ),
            ),
            const SizedBox(height: 10),
            _Option(
              icon: Icons.photo_camera_outlined,
              title: 'Take a photo of a sheet',
              subtitle: 'Read here on the phone. Lay the sheet flat, fill the '
                  'frame, keep the camera square on.',
              onTap: () => Navigator.pop(context, ImportChoice.camera),
            ),
            _Option(
              icon: Icons.photo_library_outlined,
              title: 'Choose photos',
              subtitle:
                  'Sheets already in the gallery. Several at once is fine.',
              onTap: () => Navigator.pop(context, ImportChoice.gallery),
            ),
            _Option(
              icon: Icons.folder_zip_outlined,
              title: 'Import a layout pack',
              subtitle:
                  'A .zip exported from the desktop app - the most accurate '
                  'way, and the quickest.',
              onTap: () => Navigator.pop(context, ImportChoice.pack),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    ),
  );
}

class _Option extends StatelessWidget {
  const _Option({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
        onTap: onTap,
        contentPadding: const EdgeInsets.symmetric(horizontal: 22, vertical: 6),
        leading: Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: palette.panelRaised,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: palette.border),
          ),
          child: Icon(icon, color: palette.accent, size: 22),
        ),
        title: Text(title,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Text(subtitle,
              style: const TextStyle(
                  fontSize: 12.5, color: palette.textDim, height: 1.35)),
        ),
      );
}

/// Runs the chosen import, showing what it is doing while it works.
class ImportRunner {
  ImportRunner(this.context, this.state);

  final BuildContext context;
  final AppState state;

  Future<void> run(ImportChoice choice) async {
    switch (choice) {
      case ImportChoice.pack:
        await _importPack();
      case ImportChoice.camera:
        await _importPhotos(fromCamera: true);
      case ImportChoice.gallery:
        await _importPhotos(fromCamera: false);
    }
  }

  Future<void> _importPack() async {
    final messenger = ScaffoldMessenger.of(context);
    final chosen = await FilePicker.platform.pickFiles(type: FileType.any);
    final path = chosen?.files.single.path;
    if (path == null) return;
    if (!path.toLowerCase().endsWith('.zip')) {
      messenger.showSnackBar(const SnackBar(
        content: Text('Choose the .zip layout pack exported from the desktop.'),
      ));
      return;
    }
    try {
      final result = await state.importPack(File(path));
      messenger.showSnackBar(
          SnackBar(content: Text('Imported ${result.describe()}')));
    } on PackFormatException catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    } catch (error) {
      messenger.showSnackBar(
          SnackBar(content: Text('That pack could not be read: $error')));
    }
  }

  Future<void> _importPhotos({required bool fromCamera}) async {
    final messenger = ScaffoldMessenger.of(context);
    final picker = ImagePicker();
    final List<XFile> picked;
    try {
      if (fromCamera) {
        final shot = await picker.pickImage(
            source: ImageSource.camera, imageQuality: 95);
        picked = shot == null ? const [] : [shot];
      } else {
        picked = await picker.pickMultiImage(imageQuality: 95);
      }
    } catch (error) {
      messenger.showSnackBar(SnackBar(
          content: Text('The camera or gallery could not open: $error')));
      return;
    }
    if (picked.isEmpty) return;
    if (!context.mounted) return;

    final progress = ValueNotifier<String>('Getting started...');
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (context) => _ReadingDialog(progress: progress),
    );

    try {
      final (result, warnings) = await state.importPhotos(
        [for (final file in picked) File(file.path)],
        progress: (update) => progress.value = _describe(update),
      );
      if (context.mounted) Navigator.of(context).pop();

      if (result.pages == 0) {
        messenger.showSnackBar(const SnackBar(
          content: Text('Nothing could be read from those photos.'),
        ));
        return;
      }
      if (context.mounted) {
        await _showOutcome(context, result, warnings);
      }
    } catch (error) {
      if (context.mounted) Navigator.of(context).pop();
      messenger.showSnackBar(
          SnackBar(content: Text('Those photos could not be read: $error')));
    } finally {
      progress.dispose();
    }
  }

  static String _describe(PhotoImportProgress update) {
    final of =
        update.total > 1 ? ' (${update.index + 1} of ${update.total})' : '';
    return '${update.stage[0].toUpperCase()}${update.stage.substring(1)}$of...';
  }

  Future<void> _showOutcome(
      BuildContext context, PackImportResult result, List<String> warnings) {
    return showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: palette.panel,
        title: const Text('Read from your photos'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(result.describe()),
            const SizedBox(height: 12),
            const Text(
              'Reading on the phone is rougher than on the desktop, which '
              'flattens the page first. Check a product you know before '
              'trusting it on the floor.',
              style:
                  TextStyle(fontSize: 13, color: palette.textDim, height: 1.4),
            ),
            if (warnings.isNotEmpty) ...[
              const SizedBox(height: 14),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 180),
                child: SingleChildScrollView(
                  child: Text(
                    warnings.toSet().join('\n\n'),
                    style:
                        const TextStyle(fontSize: 12.5, color: palette.amber),
                  ),
                ),
              ),
            ],
          ],
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }
}

class _ReadingDialog extends StatelessWidget {
  const _ReadingDialog({required this.progress});

  final ValueNotifier<String> progress;

  @override
  Widget build(BuildContext context) => AlertDialog(
        backgroundColor: palette.panel,
        content: Row(
          children: [
            const SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2.4),
            ),
            const SizedBox(width: 18),
            Expanded(
              child: ValueListenableBuilder<String>(
                valueListenable: progress,
                builder: (context, value, _) =>
                    Text(value, style: const TextStyle(fontSize: 14)),
              ),
            ),
          ],
        ),
      );
}
