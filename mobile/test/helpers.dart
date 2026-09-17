/// Fixtures that mirror the real "IE Household 4.5m" sheets.
library;

import 'package:shelffinder_mobile/data/models.dart';

const _page2Shelves = [
  [33, 62, 0],
  [22, 62, 0],
  [12, 62, 0],
  [3, 80, 0],
];

const _page2Products = [
  ['250810', 'The Pink Stuff Miracle Paste', 2, 1, 1, 150],
  ['217970', 'Furniture Polish Beeswax Multi', 2, 1, 1, 400],
  ['202946', 'Carpet& Upholstery Foam Cleaner', 2, 2, 1, 750],
  ['213350', 'Platinum Dishwasher Tabs 40WL', 4, 2, 1, 1000],
  ['7175141', 'All-in-1 Dishwasher Tabs 60WL', 8, 3, 1, 1300],
  ['7149115', 'All-in-1 Dishwasher Tabs Lemon 60WL', 8, 3, 1, 1500],
  ['10007181', 'Dishwasher Tablets Family Pack 80WL', 4, 3, 1, 1700],
  ['5481', 'Finish Quantum Ultimate', 2, 3, 1, 1900],
  ['7002958', 'Washing Up Liquid', 8, 1, 2, 300],
  ['7008038', 'Fairy 654ml Original', 4, 1, 3, 120],
  ['1023107', 'Fairy WUL Lemon', 2, 1, 3, 300],
  ['7190489', 'Fairy WUL Pomegranate& Grapefruit', 2, 1, 3, 480],
  ['10076121', 'Fairy Max Power 730ml', 2, 1, 3, 640],
  ['200593', 'Dishwasher Salt', 4, 2, 3, 800],
  ['204356', 'Dishwasher Cleaner', 8, 2, 3, 1050],
  ['209041', 'All Purpose Cleaner', 2, 1, 4, 200],
];

const _page1Products = [
  ['230167', 'Thick Bleach Original/Citrus', 2, 1, 1, 200],
  ['1060', 'Febreze Bathroom Spring Awakening', 3, 1, 2, 150],
  ['209041', 'All Purpose Cleaner', 2, 1, 2, 400],
  ['241709', 'Toilet Cleaner', 4, 1, 2, 650],
];

PlanogramPage _makePage(
  int number,
  int? total,
  List<List<Object>> entries,
  List<List<int>> shelves,
  int bayCount, {
  String id = '',
}) {
  final bayWidth = 2100 / bayCount;
  final bays = <Bay>[];
  for (var index = 1; index <= bayCount; index++) {
    bays.add(Bay(
      index: index,
      xRange: [(index - 1) * bayWidth, index * bayWidth],
      shelvesInherited: index > 1,
      shelves: [
        for (var shelfIndex = 1; shelfIndex <= shelves.length; shelfIndex++)
          Shelf(
            indexFromTop: shelfIndex,
            yRange: [200 + (shelfIndex - 1) * 600, 200 + shelfIndex * 600],
            notch: shelves[shelfIndex - 1][0],
            depthCm: shelves[shelfIndex - 1][1].toDouble(),
            slope: shelves[shelfIndex - 1][2].toDouble(),
            inherited: index > 1,
          ),
      ],
    ));
  }

  final products = <Product>[];
  for (final entry in entries) {
    final shelfIndex = entry[4] as int;
    final x = (entry[5] as int).toDouble();
    products.add(Product(
      code: entry[0] as String,
      name: entry[1] as String,
      cases: entry[2] as int,
      bay: entry[3] as int,
      shelf: shelfIndex,
      bbox: BBox(x, 200 + (shelfIndex - 1) * 600 + 250, 120, 90),
    ));
  }

  // Positions, exactly as the parser assigns them.
  final grouped = <String, List<Product>>{};
  for (final product in products) {
    grouped.putIfAbsent('${product.bay}:${product.shelf}', () => []).add(product);
  }
  final placed = <Product>[];
  for (final group in grouped.values) {
    group.sort((a, b) => a.bbox!.centreX.compareTo(b.bbox!.centreX));
    for (var index = 0; index < group.length; index++) {
      final product = group[index];
      placed.add(Product(
        code: product.code,
        name: product.name,
        cases: product.cases,
        bbox: product.bbox,
        bay: product.bay,
        shelf: product.shelf,
        positionLeft: index + 1,
        positionRight: group.length - index,
      ));
    }
  }

  return PlanogramPage(
    id: id.isEmpty ? 'page$number' : id,
    number: number,
    totalPages: total,
    size: const [2100, 3000],
    bays: bays,
    products: placed,
    imagePath: '',
  );
}

Layout householdLayout() => Layout(
      id: 'household',
      name: 'IE Household',
      size: '4.5m',
      importedAt: '2026-01-01T00:00:00Z',
      pages: [
        _makePage(1, 2, _page1Products, _page2Shelves.take(2).toList(), 3,
            id: 'household-1'),
        _makePage(2, 2, _page2Products, _page2Shelves, 3, id: 'household-2'),
      ],
    );

Layout frozenLayout() => Layout(
      id: 'frozen',
      name: 'IE Frozen',
      size: '2.5m',
      importedAt: '2026-01-01T00:00:00Z',
      pages: [
        _makePage(
          1,
          1,
          [
            ['5481', 'Frozen Peas', 6, 1, 1, 300],
            ['300380', 'Ice Cream Tubs', 4, 1, 1, 700],
          ],
          _page2Shelves.take(1).toList(),
          1,
          id: 'frozen-1',
        ),
      ],
    );
