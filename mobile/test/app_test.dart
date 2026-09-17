/// Drives the real screens: type a code, open the result, read the card.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shelffinder_mobile/app_state.dart';
import 'package:shelffinder_mobile/data/library_store.dart';
import 'package:shelffinder_mobile/main.dart';
import 'package:shelffinder_mobile/widgets/result_tile.dart';

void main() {
  late Directory workspace;
  late AppState state;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    workspace = await Directory.systemTemp.createTemp('shelffinder-ui');
    final store = LibraryStore(workspace);
    await store.load();
    await store.importPack(
        File(p.join('test', 'fixtures', 'household.shelfpack.zip')));
    state = AppState(store: store);
    // Start it here, where real file and preference reads can actually finish:
    // inside a widget test the clock is faked and they would never complete.
    await state.start();
  });

  tearDown(() async {
    if (await workspace.exists()) await workspace.delete(recursive: true);
  });

  /// Pumps a few frames rather than pumpAndSettle: the layouts tab holds
  /// `Image.file` thumbnails, and file images never finish loading under the
  /// test binding, so settling would wait forever.
  Future<void> settle(WidgetTester tester, [int frames = 6]) async {
    for (var index = 0; index < frames; index++) {
      await tester.pump(const Duration(milliseconds: 60));
    }
  }

  Future<void> open(WidgetTester tester) async {
    await tester.pumpWidget(ShelfFinderApp(state: state));
    await settle(tester);
  }

  testWidgets('the search screen opens with the library loaded',
      (tester) async {
    await open(tester);
    expect(find.text('Product code'), findsOneWidget);
    expect(find.text('Type three digits or more'), findsOneWidget);
  });

  testWidgets('typing a code lists the match', (tester) async {
    await open(tester);
    await tester.enterText(find.byType(TextField), '038');
    await tester.pump(const Duration(milliseconds: 200));
    await settle(tester);

    expect(find.byType(ResultTile), findsWidgets);
    expect(find.textContaining('match'), findsWidgets);
  });

  testWidgets('a short query does not search', (tester) async {
    await open(tester);
    await tester.enterText(find.byType(TextField), '03');
    await tester.pump(const Duration(milliseconds: 200));
    await settle(tester);

    expect(find.byType(ResultTile), findsNothing);
    expect(find.text('Type three digits or more'), findsOneWidget);
  });

  testWidgets('a code that is not there suggests the near misses',
      (tester) async {
    await open(tester);
    await tester.enterText(find.byType(TextField), '7008039');
    await tester.pump(const Duration(milliseconds: 200));
    await settle(tester);

    expect(find.textContaining('one slip away'), findsOneWidget);
  });

  testWidgets('opening a result shows where the product goes', (tester) async {
    await open(tester);
    await tester.enterText(find.byType(TextField), '038');
    await tester.pump(const Duration(milliseconds: 200));
    await settle(tester);

    await tester.tap(find.byType(ResultTile).first);
    await settle(tester);

    expect(find.text('BAY'), findsOneWidget);
    expect(find.text('SHELF FROM TOP'), findsOneWidget);
    expect(find.text('POSITION FROM LEFT'), findsOneWidget);
    expect(find.text('CASES'), findsOneWidget);
    expect(find.text('NEIGHBOURS'), findsOneWidget);
    expect(find.textContaining('Notch'), findsWidgets);
  });

  testWidgets('the layouts tab lists what was imported', (tester) async {
    await open(tester);
    await tester.tap(find.text('Layouts'));
    await settle(tester);

    expect(find.textContaining('Household'), findsWidgets);
    expect(find.textContaining('page(s)'), findsWidgets);
  });

  testWidgets('settings offers the highlight colours', (tester) async {
    await open(tester);
    await tester.tap(find.text('Settings'));
    await settle(tester);

    expect(find.text('HIGHLIGHT COLOUR'), findsOneWidget);
    expect(find.text('Cyan'), findsOneWidget);
    await tester.tap(find.text('Cyan'));
    await settle(tester);
    expect(state.highlight, const Color(0xFF29E0E3));
  });

  testWidgets('the add button offers photos as well as a pack', (tester) async {
    await open(tester);
    await tester.tap(find.text('Layouts'));
    await settle(tester);
    await tester.tap(find.text('Add sheets'));
    await settle(tester);

    expect(find.text('Take a photo of a sheet'), findsOneWidget);
    expect(find.text('Choose photos'), findsOneWidget);
    expect(find.text('Import a layout pack'), findsOneWidget);
  });

  testWidgets('a product can be fixed from the viewer', (tester) async {
    await open(tester);
    await tester.enterText(find.byType(TextField), '038');
    await tester.pump(const Duration(milliseconds: 200));
    await settle(tester);
    await tester.tap(find.byType(ResultTile).first);
    await settle(tester);

    // The button sits at the bottom of the details sheet, which scrolls.
    final fixButton = find.textContaining('Fix it');
    await tester.ensureVisible(fixButton);
    await settle(tester);
    await tester.tap(fixButton);
    await settle(tester, 12);
    expect(find.text('Fix this product'), findsOneWidget);

    final codeField = find.widgetWithText(TextField, '7008038');
    expect(codeField, findsOneWidget);
    await tester.enterText(find.byType(TextField).first, '7008777');
    await tester.tap(find.text('Save'));
    await settle(tester, 12);

    // The correction is saved, and search finds the code it now carries.
    expect(state.index.search('7008777').hits, isNotEmpty);
    expect(state.index.search('7008038').hits, isEmpty);
  });

  testWidgets('the layouts tab offers what needs checking', (tester) async {
    // Make one product look doubtful, the way a phone-read sheet would.
    final page = state.layouts.first.pages.first;
    page.products = [
      for (final product in page.products)
        product == page.products.first
            ? product.copyWith(confidence: 0.2)
            : product,
    ];

    await open(tester);
    await tester.tap(find.text('Layouts'));
    await settle(tester);
    expect(find.textContaining('worth checking'), findsOneWidget);

    await tester.tap(find.textContaining('worth checking'));
    await settle(tester);
    expect(find.text('To check'), findsOneWidget);
    expect(find.text('Fix'), findsWidgets);
  });

  testWidgets('with nothing imported the app asks for a pack', (tester) async {
    late Directory empty;
    late AppState emptyState;
    // runAsync steps outside the faked clock, so the real file reads finish.
    await tester.runAsync(() async {
      empty = await Directory.systemTemp.createTemp('shelffinder-empty');
      final store = LibraryStore(empty);
      await store.load();
      emptyState = AppState(store: store);
      await emptyState.start();
    });

    await tester.pumpWidget(ShelfFinderApp(state: emptyState));
    await settle(tester);

    expect(find.text('No layouts yet'), findsOneWidget);
    expect(find.text('Add layout sheets'), findsOneWidget);
    await tester.runAsync(() => empty.delete(recursive: true));
  });
}
