/// Reads a pack the desktop app actually exported, not a hand-written one.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:shelffinder_mobile/data/library_store.dart';
import 'package:shelffinder_mobile/data/search.dart';

File fixture() =>
    File(p.join('test', 'fixtures', 'household.shelfpack.zip'));

void main() {
  late Directory workspace;
  late LibraryStore store;

  setUp(() async {
    workspace = await Directory.systemTemp.createTemp('shelffinder-test');
    store = LibraryStore(workspace);
    await store.load();
  });

  tearDown(() async {
    if (await workspace.exists()) await workspace.delete(recursive: true);
  });

  test('a pack exported by the desktop app imports and is searchable', () async {
    final result = await store.importPack(fixture());

    expect(result.layouts, 1);
    expect(result.pages, 2);
    expect(result.products, greaterThan(50));
    expect(store.layouts.single.title, contains('Household'));

    final search = store.index.search('038');
    expect(search.hits, isNotEmpty);
    expect(search.hits.first.product.code, endsWith('038'));
  });

  test('page images land on the device and the pages point at them', () async {
    await store.importPack(fixture());
    for (final page in store.layouts.single.pages) {
      expect(page.imagePath, isNotEmpty);
      expect(await File(page.imagePath).exists(), isTrue);
      expect(page.width, greaterThan(0));
      expect(page.height, greaterThan(0));
    }
  });

  test('shelves, bays and positions survive the trip', () async {
    await store.importPack(fixture());
    final pages = store.layouts.single.pages;
    final shelves = [
      for (final page in pages)
        for (final bay in page.bays)
          for (final shelf in bay.shelves) shelf.notch,
    ];
    expect(shelves, contains(33));
    expect(shelves.where((notch) => notch != null), isNotEmpty);

    final product = pages
        .expand((page) => page.products)
        .firstWhere((product) => product.positionLeft > 0);
    expect(product.bay, greaterThan(0));
    expect(product.shelf, greaterThan(0));
    expect(product.bbox, isNotNull);
  });

  test('what was imported is still there next time the app opens', () async {
    await store.importPack(fixture());
    final before = store.productCount;

    final reopened = LibraryStore(workspace);
    await reopened.load();
    expect(reopened.productCount, before);
    expect(reopened.index.search('038').hits, isNotEmpty);
  });

  test('importing the same layout again replaces it rather than doubling it',
      () async {
    await store.importPack(fixture());
    final first = store.productCount;
    await store.importPack(fixture());

    expect(store.layouts.length, 1);
    expect(store.productCount, first);
  });

  test('a zip that is not a layout pack says so plainly', () async {
    final notAPack = File(p.join(workspace.path, 'random.zip'));
    // A valid but empty zip archive.
    await notAPack.writeAsBytes(
        [80, 75, 5, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);

    expect(
      () => store.importPack(notAPack),
      throwsA(isA<PackFormatException>()
          .having((error) => error.message, 'message', contains('pack.json'))),
    );
  });

  test('a layout can be removed again', () async {
    await store.importPack(fixture());
    final layoutId = store.layouts.single.id;
    await store.deleteLayout(layoutId);

    expect(store.layouts, isEmpty);
    expect(store.index.search('038').hits, isEmpty);
  });
}
