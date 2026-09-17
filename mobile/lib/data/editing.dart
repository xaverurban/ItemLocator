/// Corrections made on the phone, and the bookkeeping that follows them.
///
/// The phone cannot flatten a page, so what it reads from a photo needs fixing
/// more often than what the desktop reads. These are the same rules the desktop
/// applies: a correction counts as checked, and a shelf renumbers when
/// something leaves it.
library;

import 'models.dart';

/// Number the products along each shelf, from the left and from the right.
List<Product> assignPositions(List<Product> products) {
  final grouped = <String, List<Product>>{};
  for (final product in products) {
    grouped.putIfAbsent('${product.bay}:${product.shelf}', () => []).add(product);
  }
  final placed = <Product>[];
  for (final group in grouped.values) {
    group.sort((a, b) => (a.bbox?.centreX ?? 0).compareTo(b.bbox?.centreX ?? 0));
    for (var index = 0; index < group.length; index++) {
      placed.add(group[index].copyWith(
        positionLeft: index + 1,
        positionRight: group.length - index,
      ));
    }
  }
  return placed;
}

Product _checked(Product product) => product.copyWith(
      confidence: 1,
      manuallyEdited: true,
      tags: [
        for (final tag in product.tags)
          if (tag != 'unreadable' && tag != 'unplaced') tag,
      ],
    );

/// Apply a correction to one product and hand back the page's new product list.
List<Product> updateProduct(
  PlanogramPage page,
  Product product, {
  String? code,
  String? name,
  int? cases,
  bool clearCases = false,
}) {
  final digits =
      code?.split('').where((c) => RegExp(r'\d').hasMatch(c)).join();
  final corrected = _checked(product.copyWith(
    code: digits,
    name: name?.trim(),
    cases: cases,
    clearCases: clearCases,
  ));

  final updated = [
    for (final other in page.products)
      identical(other, product) ? corrected : other,
  ];
  return assignPositions(updated);
}

/// Remove a product - a box round something that is not a product - and
/// renumber what is left on that shelf.
List<Product> deleteProduct(PlanogramPage page, Product product) {
  final remaining = [
    for (final other in page.products)
      if (!identical(other, product)) other,
  ];
  return assignPositions(remaining);
}

class ReviewSummary {
  const ReviewSummary({
    required this.total,
    required this.needsChecking,
    required this.missingName,
    required this.missingCases,
    required this.baysSharingShelves,
  });

  final int total;
  final int needsChecking;
  final int missingName;
  final int missingCases;
  final List<int> baysSharingShelves;

  bool get isClean => needsChecking == 0 && baysSharingShelves.isEmpty;

  String describe() {
    if (total == 0) return 'Nothing was read from this page.';
    final parts = <String>['$total products'];
    if (needsChecking > 0) parts.add('$needsChecking to check');
    if (baysSharingShelves.isNotEmpty) {
      parts.add('bay ${baysSharingShelves.join(', ')} sharing shelves');
    }
    return parts.join(' · ');
  }
}

ReviewSummary reviewSummary(PlanogramPage page) => ReviewSummary(
      total: page.products.length,
      needsChecking:
          page.products.where((product) => product.needsChecking).length,
      missingName: page.products.where((product) => product.name.isEmpty).length,
      missingCases: page.products.where((product) => product.cases == null).length,
      baysSharingShelves: [
        for (final bay in page.bays)
          if (bay.shelvesInherited) bay.index,
      ],
    );

/// Everything on a layout that a person should look at, worst first.
List<(PlanogramPage, Product)> productsToCheck(Layout layout) {
  final found = <(PlanogramPage, Product)>[];
  for (final page in layout.pages) {
    for (final product in page.products) {
      if (product.needsChecking) found.add((page, product));
    }
  }
  found.sort((a, b) {
    final byConfidence = a.$2.confidence.compareTo(b.$2.confidence);
    if (byConfidence != 0) return byConfidence;
    final byPage = a.$1.number.compareTo(b.$1.number);
    if (byPage != 0) return byPage;
    return a.$2.bay.compareTo(b.$2.bay);
  });
  return found;
}
