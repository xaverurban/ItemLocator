/// The file handling around reading a photo - the part that does not need
/// ML Kit, and the part that broke on a real phone.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:shelffinder_mobile/data/library_store.dart';
import 'package:shelffinder_mobile/data/photo_import.dart';

void main() {
  late Directory workspace;

  setUp(() async {
    workspace = await Directory.systemTemp.createTemp('shelffinder-photo');
  });

  tearDown(() async {
    if (await workspace.exists()) await workspace.delete(recursive: true);
  });

  test('reading a photo works on a fresh install, with no folders yet', () async {
    // Nothing has been imported, so nothing has created the images folder.
    final images = Directory(p.join(workspace.path, 'library', 'images'));
    expect(await images.exists(), isFalse);

    final importer = PhotoImporter(imagesDirectory: images);
    final scratch = await importer.prepare();

    expect(await images.exists(), isTrue,
        reason: 'writing a page image must have somewhere to go');
    expect(await scratch.exists(), isTrue);

    // A file can actually be written there, which is what used to fail with
    // PathNotFoundException.
    final probe = File(p.join(images.path, 'probe.jpg'));
    await probe.writeAsBytes([1, 2, 3]);
    expect(await probe.exists(), isTrue);

    await importer.dispose();
    expect(await scratch.exists(), isFalse, reason: 'scratch is cleaned up');
  });

  test('turning a photo does not leave working files in the library', () async {
    final images = Directory(p.join(workspace.path, 'library', 'images'));
    final importer = PhotoImporter(imagesDirectory: images);
    final scratch = await importer.prepare();

    // The rotation trials belong in the scratch folder, not beside the pages.
    await File(p.join(scratch.path, 'page.turn90.jpg')).writeAsBytes([1]);
    expect(images.listSync(), isEmpty);

    await importer.dispose();
  });

  test('a store opens cleanly on a device that has never imported anything',
      () async {
    final store = LibraryStore(Directory(p.join(workspace.path, 'library')));
    await store.load();

    expect(await store.imagesDirectory.exists(), isTrue);
    expect(store.layouts, isEmpty);
    expect(store.productCount, 0);
  });
}
