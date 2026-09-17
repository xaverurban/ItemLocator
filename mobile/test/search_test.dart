import 'package:flutter_test/flutter_test.dart';
import 'package:shelffinder_mobile/data/search.dart';

import 'helpers.dart';

void main() {
  late ProductIndex index;

  setUp(() {
    index = ProductIndex([householdLayout(), frozenLayout()]);
  });

  test('a query shorter than three digits does not search', () {
    for (final query in ['', '0', '03']) {
      final result = index.search(query);
      expect(result.tooShort, isTrue);
      expect(result.hits, isEmpty);
    }
    expect(index.search('038').tooShort, isFalse);
  });

  test('ends-with beats contains', () {
    final result = index.search('038');
    expect(result.hits.first.product.code, '7008038');
    expect(result.hits.first.kind, MatchKind.suffix);
    expect(result.hits.map((hit) => hit.kind).toList(),
        [MatchKind.suffix, MatchKind.contains]);
  });

  test('an exact code sorts first and every location is listed', () {
    final result = index.search('5481');
    expect(result.hits.first.kind, MatchKind.exact);
    expect(result.hits.length, 2);
    expect(result.hits.map((hit) => hit.layout.name).toSet(),
        {'IE Household', 'IE Frozen'});
  });

  test('one match in a single layout is the one to jump to', () {
    final result = index.search('038', layoutId: householdLayout().id);
    expect(result.single, isNotNull);
    expect(result.single!.product.code, '7008038');
  });

  test('typed letters are read as the digits they look like', () {
    expect(index.search('o38').hits.first.product.code, '7008038');
    expect(normaliseCode('l0176277'), '10176277');
  });

  test('a wrong digit still leads somewhere', () {
    final result = index.search('7008039');
    expect(result.isEmpty, isTrue);
    expect(result.suggestions.map((hit) => hit.product.code), contains('7008038'));
    expect(result.suggestions.first.reason, 'one digit different');
    expect(result.message, contains('Did you mean'));
  });

  test('two swapped digits are suggested too', () {
    final result = index.search('7149151');
    expect(result.isEmpty, isTrue);
    expect(result.suggestions.map((hit) => hit.product.code), contains('7149115'));
  });

  test('the same code on two shelves keeps both places', () {
    final result = index.search('209041');
    expect(result.hits.length, 2);
    expect(result.hits.map((hit) => hit.page.number).toSet(), {1, 2});
  });

  test('nothing at all says what was searched for', () {
    final result = index.search('999');
    expect(result.isEmpty, isTrue);
    expect(result.message, startsWith('No product ending in 999'));
  });

  test('the matched digits are marked for the list to embolden', () {
    final hit = index.search('038').hits.first;
    final (before, matched, after) = hit.highlight();
    expect(before, '7008');
    expect(matched, '038');
    expect(after, '');
  });

  test('a tap on the page finds the product under it', () {
    final layout = householdLayout();
    final page = layout.pages[1];
    final product = page.products.firstWhere((p) => p.code == '7008038');
    final found = ProductIndex([layout])
        .productAt(page, product.bbox!.centreX, product.bbox!.centreY);
    expect(found?.code, '7008038');
  });
}
