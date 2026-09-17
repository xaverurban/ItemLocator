/// Where the phone keeps imported layouts: a JSON file and a folder of images.
library;

import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:path/path.dart' as p;

import 'models.dart';
import 'photo_parser.dart';
import 'search.dart';

const int packSchemaVersion = 1;

class PackImportResult {
  const PackImportResult(this.layouts, this.pages, this.products);

  final int layouts;
  final int pages;
  final int products;

  String describe() =>
      '$layouts layout${layouts == 1 ? '' : 's'}, $pages page${pages == 1 ? '' : 's'}, '
      '$products products';
}

class PackFormatException implements Exception {
  PackFormatException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Reads ShelfFinder layout packs and keeps what it finds on the device.
class LibraryStore {
  LibraryStore(this.directory);

  final Directory directory;
  final List<Layout> layouts = [];
  final ProductIndex index = ProductIndex();

  File get _manifest => File(p.join(directory.path, 'library.json'));
  Directory get imagesDirectory => Directory(p.join(directory.path, 'images'));

  int get productCount =>
      layouts.fold(0, (total, layout) => total + layout.productCount);
  int get pageCount =>
      layouts.fold(0, (total, layout) => total + layout.pages.length);

  Future<void> load() async {
    layouts.clear();
    if (await _manifest.exists()) {
      try {
        final payload =
            jsonDecode(await _manifest.readAsString()) as Map<String, dynamic>;
        for (final entry in (payload['layouts'] as List? ?? const [])) {
          layouts.add(Layout.fromJson(entry as Map<String, dynamic>));
        }
      } on FormatException {
        // A half-written file should not stop the app from opening.
        await _manifest.delete();
      }
    }
    index.rebuild(layouts);
  }

  Future<void> save() async {
    // Rebuild first: search should reflect a correction the moment it is made,
    // not once the file has finished being written.
    index.rebuild(layouts);
    await directory.create(recursive: true);
    await _manifest.writeAsString(jsonEncode({
      'schema_version': packSchemaVersion,
      'layouts': [for (final layout in layouts) layout.toStoredJson()],
    }));
  }

  /// Read a `.zip` layout pack exported by the desktop app.
  Future<PackImportResult> importPack(File file) async {
    final archive = ZipDecoder().decodeBytes(await file.readAsBytes());

    ArchiveFile? manifestEntry;
    for (final entry in archive.files) {
      if (entry.name == 'pack.json') manifestEntry = entry;
    }
    if (manifestEntry == null) {
      throw PackFormatException(
          'That zip is not a ShelfFinder layout pack - it has no pack.json. '
          'Export one from the desktop app.');
    }

    final payload = jsonDecode(utf8.decode(manifestEntry.content as List<int>))
        as Map<String, dynamic>;
    final version = (payload['schema_version'] as num?)?.toInt() ?? 0;
    if (version > packSchemaVersion) {
      throw PackFormatException(
          'This pack was made by a newer version of ShelfFinder '
          '(pack format $version, this app reads $packSchemaVersion). '
          'Update the app.');
    }

    await imagesDirectory.create(recursive: true);
    final byName = {for (final entry in archive.files) entry.name: entry};

    var pages = 0;
    var products = 0;
    final imported = <Layout>[];
    for (final document in (payload['layouts'] as List? ?? const [])) {
      final layout = Layout.fromJson(document as Map<String, dynamic>);
      for (final page in layout.pages) {
        pages += 1;
        products += page.products.length;
        final inside = page.imagePath;
        final entry = byName[inside];
        if (inside.isEmpty || entry == null) {
          page.imagePath = '';
          continue;
        }
        final target = File(p.join(imagesDirectory.path, p.basename(inside)));
        await target.writeAsBytes(entry.content as List<int>);
        page.imagePath = target.path;
      }
      imported.add(layout);
    }

    // A pack replaces the layout it carries: re-importing a corrected sheet
    // should not leave the old copy behind for search to find.
    for (final layout in imported) {
      layouts.removeWhere((existing) =>
          _squash(existing.title) == _squash(layout.title) ||
          existing.id == layout.id);
    }
    layouts.addAll(imported);
    layouts.sort((a, b) => a.title.toLowerCase().compareTo(b.title.toLowerCase()));
    await save();
    return PackImportResult(imported.length, pages, products);
  }

  /// Store pages read from photos on this phone, grouped into layouts by header.
  Future<PackImportResult> addPhotoPages(List<PhotoParseResult> results) async {
    await imagesDirectory.create(recursive: true);
    var pages = 0;
    var products = 0;
    final touched = <String>{};

    for (final result in results) {
      final title = '\${result.layoutName} \${result.layoutSize}'.trim();
      final key = _squash(title);
      pages += 1;
      products += result.page.products.length;

      Layout? existing;
      for (final layout in layouts) {
        if (_squash(layout.title) == key && key.isNotEmpty) existing = layout;
      }
      if (existing == null) {
        existing = Layout(
          id: 'phone-\${DateTime.now().microsecondsSinceEpoch}-\${layouts.length}',
          name: result.layoutName.isEmpty ? 'Photographed sheet' : result.layoutName,
          size: result.layoutSize,
          importedAt: DateTime.now().toUtc().toIso8601String(),
          pages: [],
        );
        layouts.add(existing);
      }
      // A new photo of a page replaces the old reading of that page.
      existing.pages.removeWhere((page) => page.number == result.page.number);
      existing.pages.add(result.page);
      existing.pages.sort((a, b) => a.number.compareTo(b.number));
      touched.add(existing.id);
    }

    layouts.sort((a, b) => a.title.toLowerCase().compareTo(b.title.toLowerCase()));
    await save();
    return PackImportResult(touched.length, pages, products);
  }

  Future<void> deleteLayout(String layoutId) async {
    final going = layouts.where((layout) => layout.id == layoutId).toList();
    for (final layout in going) {
      for (final page in layout.pages) {
        if (page.imagePath.isEmpty) continue;
        final file = File(page.imagePath);
        if (await file.exists()) await file.delete();
      }
    }
    layouts.removeWhere((layout) => layout.id == layoutId);
    await save();
  }

  Layout? layoutOf(PlanogramPage page) {
    for (final layout in layouts) {
      if (layout.pages.any((other) => other.id == page.id)) return layout;
    }
    return null;
  }

  static String _squash(String text) =>
      text.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
}
