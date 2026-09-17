import 'package:flutter_test/flutter_test.dart';
import 'package:shelffinder_mobile/data/locate.dart';
import 'package:shelffinder_mobile/data/models.dart';

import 'helpers.dart';

Product find(Layout layout, String code, {int page = 2}) {
  final wanted = layout.pages.firstWhere((p) => p.number == page);
  return wanted.products.firstWhere((product) => product.code == code);
}

PlanogramPage pageOf(Layout layout, int number) =>
    layout.pages.firstWhere((page) => page.number == number);

void main() {
  test('the card reads the way the shelf does', () {
    final layout = householdLayout();
    final page = pageOf(layout, 2);
    final card = locate(find(layout, '7008038'), page, layout);

    expect(card.pageLabel, 'IE Household 4.5m, page 2 of 2');
    expect(card.bayIndex, 1);
    expect(card.bayCount, 3);
    expect(card.shelfFromTop, 3);
    expect(card.shelfFromBottom, 2);
    expect(card.positionLeft, 1);
    expect(card.positionRight, 4);
    expect(card.positionCount, 4);
    expect(card.cases, 4);
    expect(card.notchLabel, 'Notch 12 · depth 62cm · slope 0');
  });

  test('the last product of a bay has its right neighbour in the next bay', () {
    final layout = householdLayout();
    final page = pageOf(layout, 2);
    final card = locate(find(layout, '10076121'), page, layout);

    expect(card.neighbourLeft?.code, '7190489');
    expect(card.neighbourRight?.code, '200593');
    expect(card.neighbourRight?.sameBay, isFalse);
    expect(card.neighbourRight?.describe(), endsWith('(next bay)'));
  });

  test('the first product on a row has nothing to its left', () {
    final layout = householdLayout();
    final card = locate(find(layout, '250810'), pageOf(layout, 2), layout);
    expect(card.neighbourLeft, isNull);
    expect(card.neighbourRight?.code, '217970');
  });

  test('a shelf run crosses every bay', () {
    final layout = householdLayout();
    final page = pageOf(layout, 2);
    final row = shelfRowProducts(page, find(layout, '213350'))
        .map((product) => product.code)
        .toList();
    expect(row, [
      '250810',
      '217970',
      '202946',
      '213350',
      '7175141',
      '7149115',
      '10007181',
      '5481',
    ]);
  });

  test('the shelf above is not a neighbour', () {
    final layout = householdLayout();
    final page = pageOf(layout, 2);
    final row = shelfRowProducts(page, find(layout, '7002958'));
    expect(row.map((product) => product.code), ['7002958']);
  });

  test('a bay that borrows its shelves is flagged for checking', () {
    final layout = householdLayout();
    final page = pageOf(layout, 2);
    expect(locate(find(layout, '213350'), page, layout).needsChecking, isTrue);
    expect(locate(find(layout, '7008038'), page, layout).needsChecking, isFalse);
  });

  test('a reversed customer flow turns the bays and neighbours round', () {
    final layout = householdLayout();
    final original = pageOf(layout, 2);
    final flipped = PlanogramPage(
      id: original.id,
      number: original.number,
      totalPages: original.totalPages,
      size: original.size,
      bays: original.bays,
      products: original.products,
      customerFlowReversed: true,
    );
    final card = locate(find(layout, '10076121'), flipped, layout);
    expect(card.bayIndex, 3);
    expect(card.neighbourLeft?.code, '200593');
    expect(card.neighbourRight?.code, '7190489');
  });
}
