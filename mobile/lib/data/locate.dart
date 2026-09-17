/// Turning a hit into the numbers a worker needs on the shop floor.
library;

import 'models.dart';

class Neighbour {
  const Neighbour(this.code, this.name, this.sameBay);

  final String code;
  final String name;
  final bool sameBay;

  String describe() {
    final label = '$code $name'.trim();
    return sameBay ? label : '$label (next bay)';
  }
}

class Location {
  Location({
    required this.product,
    required this.page,
    required this.layout,
    required this.bay,
    required this.shelf,
    required this.bayIndex,
    required this.bayCount,
    required this.shelfFromTop,
    required this.shelfFromBottom,
    required this.positionLeft,
    required this.positionRight,
    required this.positionCount,
    this.neighbourLeft,
    this.neighbourRight,
  });

  final Product product;
  final PlanogramPage page;
  final Layout layout;
  final Bay? bay;
  final Shelf? shelf;
  final int bayIndex;
  final int bayCount;
  final int shelfFromTop;
  final int shelfFromBottom;
  final int positionLeft;
  final int positionRight;
  final int positionCount;
  final Neighbour? neighbourLeft;
  final Neighbour? neighbourRight;

  String get code => product.code;
  String get name => product.name;
  int? get cases => product.cases;

  bool get needsChecking =>
      product.needsChecking || (bay?.shelvesInherited ?? false);

  String get pageLabel {
    final title = layout.title.isEmpty ? 'Unknown layout' : layout.title;
    return page.totalPages == null
        ? '$title, page ${page.number}'
        : '$title, page ${page.number} of ${page.totalPages}';
  }

  String get notchLabel {
    if (shelf?.notch == null) return 'Notch unknown';
    final parts = <String>['Notch ${shelf!.notch}'];
    if (shelf!.depthCm != null) {
      parts.add('depth ${_tidy(shelf!.depthCm!)}cm');
    }
    if (shelf!.slope != null) parts.add('slope ${_tidy(shelf!.slope!)}');
    return parts.join(' · ');
  }

  static String _tidy(double value) =>
      value == value.roundToDouble() ? '${value.round()}' : '$value';
}

/// Every product on the same physical shelf run, across bay lines, left to right.
///
/// Bays number their shelves independently, so the run is worked out from the
/// height bands the shelves occupy rather than from the shelf number.
List<Product> shelfRowProducts(PlanogramPage page, Product product) {
  final shelf = page.shelfOf(product);
  if (shelf == null || shelf.bottom <= shelf.top) {
    final sameShelf =
        page.products.where((other) => other.shelf == product.shelf).toList();
    sameShelf.sort((a, b) =>
        (a.bbox?.centreX ?? 0).compareTo(b.bbox?.centreX ?? 0));
    return sameShelf;
  }

  final height = shelf.bottom - shelf.top;
  final row = <Product>[];
  for (final candidate in page.products) {
    if (candidate.bbox == null) continue;
    final other = page.shelfOf(candidate);
    if (other != null && other.bottom > other.top) {
      final overlap = (shelf.bottom < other.bottom ? shelf.bottom : other.bottom) -
          (shelf.top > other.top ? shelf.top : other.top);
      final shorter =
          height < (other.bottom - other.top) ? height : other.bottom - other.top;
      if (overlap <= 0 || overlap < shorter * 0.5) continue;
    } else if (candidate.bbox!.centreY < shelf.top ||
        candidate.bbox!.centreY > shelf.bottom) {
      continue;
    }
    row.add(candidate);
  }
  if (!row.contains(product)) row.add(product);
  row.sort((a, b) => (a.bbox?.centreX ?? 0).compareTo(b.bbox?.centreX ?? 0));
  return row;
}

Location locate(Product product, PlanogramPage page, Layout layout) {
  final bay = page.bayOf(product);
  final shelf = page.shelfOf(product);
  final shelfCount = bay?.shelves.length ?? 0;
  final shelfFromBottom =
      shelfCount > 0 && product.shelf > 0 ? shelfCount - product.shelf + 1 : 0;
  final positionCount = product.positionLeft + product.positionRight - 1;

  final row = shelfRowProducts(page, product);
  final index = row.indexOf(product);
  Neighbour? left;
  Neighbour? right;
  if (index > 0) {
    final other = row[index - 1];
    left = Neighbour(other.code, other.name, other.bay == product.bay);
  }
  if (index >= 0 && index + 1 < row.length) {
    final other = row[index + 1];
    right = Neighbour(other.code, other.name, other.bay == product.bay);
  }
  if (page.customerFlowReversed) {
    final swap = left;
    left = right;
    right = swap;
  }

  final bayIndex = page.customerFlowReversed && product.bay > 0
      ? (page.bays.length - product.bay + 1).clamp(1, page.bays.length)
      : product.bay;

  return Location(
    product: product,
    page: page,
    layout: layout,
    bay: bay,
    shelf: shelf,
    bayIndex: bayIndex,
    bayCount: page.bays.length,
    shelfFromTop: product.shelf,
    shelfFromBottom: shelfFromBottom,
    positionLeft: product.positionLeft,
    positionRight: product.positionRight,
    positionCount: positionCount < 0 ? 0 : positionCount,
    neighbourLeft: left,
    neighbourRight: right,
  );
}
