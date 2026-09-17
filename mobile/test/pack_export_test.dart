/// A pack written on the phone has to be one the desktop - and the phone - reads.
library;

import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:shelffinder_mobile/data/library_store.dart';
import 'package:shelffinder_mobile/data/pack_export.dart';

void main() {
  late Directory workspace;
  late LibraryStore store;

  setUp(() async {
    workspace = await Directory.systemTemp.createTemp('shelffinder-export');
    store = LibraryStore(workspace);
    await store.load();
    await store.importPack(
        File(p.join('test', 'fixtures', 'household.shelfpack.zip')));
  });

  tearDown(() async {
    if (await workspace.exists()) await workspace.delete(recursive: true);
  });

  test('a pack written here can be read back here', () async {
    final layout = store.layouts.single;
    final destination = File(p.join(workspace.path, packFileName(layout)));
    final written = await exportPack([layout], destination);

    expect(written.pages, layout.pages.length);
    expect(written.products, layout.productCount);
    expect(await destination.exists(), isTrue);
    expect(written.describe(), contains('products'));

    final reopened = LibraryStore(
        await Directory.systemTemp.createTemp('shelffinder-reimport'));
    await reopened.load();
    final result = await reopened.importPack(destination);

    expect(result.pages, layout.pages.length);
    expect(reopened.productCount, layout.productCount);
    expect(reopened.index.search('038').hits, isNotEmpty);
    await reopened.directory.delete(recursive: true);
  });

  test('the manifest is the format the desktop writes', () async {
    final destination = File(p.join(workspace.path, 'out.zip'));
    await exportPack(store.layouts, destination);

    final archive = ZipDecoder().decodeBytes(await destination.readAsBytes());
    final manifest = archive.files.firstWhere((file) => file.name == 'pack.json');
    final payload =
        jsonDecode(utf8.decode(manifest.content as List<int>)) as Map<String, dynamic>;

    expect(payload['schema_version'], packSchemaVersion);
    expect(payload['generator'], 'shelffinder-android');
    final page = (payload['layouts'] as List).first['pages'][0];
    expect(page['straightened_image'], startsWith('images/'));
    expect(archive.files.any((file) => file.name.startsWith('images/')), isTrue);
  });

  test('corrections made on the phone travel with the pack', () async {
    final layout = store.layouts.single;
    final sheet = layout.pages.first;
    sheet.products = [
      for (final product in sheet.products)
        product == sheet.products.first
            ? product.copyWith(name: 'Corrected by hand', manuallyEdited: true)
            : product,
    ];
    await store.save();

    final destination = File(p.join(workspace.path, 'out.zip'));
    await exportPack([layout], destination);

    final reopened = LibraryStore(
        await Directory.systemTemp.createTemp('shelffinder-reimport2'));
    await reopened.load();
    await reopened.importPack(destination);
    final first = reopened.layouts.single.pages.first.products.first;

    expect(first.name, 'Corrected by hand');
    expect(first.manuallyEdited, isTrue);
    await reopened.directory.delete(recursive: true);
  });

  test('a layout name becomes a sensible file name', () {
    final layout = store.layouts.single;
    expect(packFileName(layout), endsWith('.shelfpack.zip'));
    expect(packFileName(layout), isNot(contains(' ')));
  });
}
