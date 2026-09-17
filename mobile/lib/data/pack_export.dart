/// Writing a layout pack from the phone, in the format the desktop reads.
///
/// A sheet photographed at the shelf, corrected on the phone, can go back to
/// the desktop - or to a colleague's phone - as the same zip the desktop
/// exports.
library;

import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:path/path.dart' as p;

import 'library_store.dart';
import 'models.dart';

class ExportedPack {
  const ExportedPack(this.file, this.layouts, this.pages, this.products);

  final File file;
  final int layouts;
  final int pages;
  final int products;

  String describe() =>
      '$layouts layout${layouts == 1 ? '' : 's'}, $pages page${pages == 1 ? '' : 's'}, '
      '$products products';
}

/// Write [layouts] to a pack zip at [destination].
Future<ExportedPack> exportPack(
  List<Layout> layouts,
  File destination,
) async {
  final archive = Archive();
  var pages = 0;
  var products = 0;

  final documents = <Map<String, dynamic>>[];
  for (final layout in layouts) {
    final document = layout.toStoredJson();
    final storedPages = document['pages'] as List;
    for (var index = 0; index < layout.pages.length; index++) {
      final page = layout.pages[index];
      pages += 1;
      products += page.products.length;

      final inside = 'images/${page.id}.jpg';
      final image = File(page.imagePath);
      if (page.imagePath.isNotEmpty && await image.exists()) {
        final bytes = await image.readAsBytes();
        archive.addFile(ArchiveFile(inside, bytes.length, bytes));
        (storedPages[index] as Map<String, dynamic>)['straightened_image'] = inside;
      } else {
        (storedPages[index] as Map<String, dynamic>)['straightened_image'] = '';
      }
      (storedPages[index] as Map<String, dynamic>)['original_image'] = '';
    }
    documents.add(document);
  }

  final manifest = jsonEncode({
    'schema_version': packSchemaVersion,
    'exported_at': DateTime.now().toUtc().toIso8601String(),
    'generator': 'shelffinder-android',
    'layouts': documents,
  });
  final manifestBytes = utf8.encode(manifest);
  archive.addFile(ArchiveFile('pack.json', manifestBytes.length, manifestBytes));

  final encoded = ZipEncoder().encode(archive);
  if (encoded == null) {
    throw StateError('the pack could not be written');
  }
  await destination.parent.create(recursive: true);
  await destination.writeAsBytes(encoded);
  return ExportedPack(destination, layouts.length, pages, products);
}

/// A sensible file name for a layout, safe on any filesystem.
String packFileName(Layout layout) {
  final title = layout.title.isEmpty ? 'shelffinder' : layout.title;
  final safe = title
      .replaceAll(RegExp(r'[^A-Za-z0-9]+'), '-')
      .replaceAll(RegExp(r'^-+|-+$'), '')
      .toLowerCase();
  return '${safe.isEmpty ? 'shelffinder' : safe}.shelfpack.zip';
}

/// Where exports go: a folder the user can find again over USB.
Future<Directory> exportDirectory(Directory documents) async {
  final folder = Directory(p.join(documents.path, 'exports'));
  await folder.create(recursive: true);
  return folder;
}
