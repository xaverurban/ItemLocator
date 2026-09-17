/// The data model, mirroring the JSON a ShelfFinder layout pack carries.
library;

class BBox {
  const BBox(this.x, this.y, this.w, this.h);

  final double x;
  final double y;
  final double w;
  final double h;

  double get right => x + w;
  double get bottom => y + h;
  double get centreX => x + w / 2;
  double get centreY => y + h / 2;

  bool contains(double px, double py) =>
      px >= x && px <= right && py >= y && py <= bottom;

  static BBox? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    return BBox(
      (json['x'] as num).toDouble(),
      (json['y'] as num).toDouble(),
      (json['w'] as num).toDouble(),
      (json['h'] as num).toDouble(),
    );
  }
}

class Product {
  Product({
    required this.code,
    required this.name,
    this.cases,
    this.bbox,
    this.imageBbox,
    this.bay = 0,
    this.shelf = 0,
    this.positionLeft = 0,
    this.positionRight = 0,
    this.confidence = 1,
    this.tags = const [],
    this.manuallyEdited = false,
  });

  final String code;
  final String name;
  final int? cases;
  final BBox? bbox;
  final BBox? imageBbox;
  final int bay;
  final int shelf;
  final int positionLeft;
  final int positionRight;
  final double confidence;
  final List<String> tags;
  final bool manuallyEdited;

  bool get needsChecking =>
      confidence < 0.72 || name.isEmpty || tags.contains('unreadable');

  factory Product.fromJson(Map<String, dynamic> json) => Product(
        code: (json['code'] ?? '') as String,
        name: (json['name'] ?? '') as String,
        cases: (json['cases'] as num?)?.toInt(),
        bbox: BBox.fromJson(json['bbox'] as Map<String, dynamic>?),
        imageBbox: BBox.fromJson(json['image_bbox'] as Map<String, dynamic>?),
        bay: (json['bay'] as num?)?.toInt() ?? 0,
        shelf: (json['shelf'] as num?)?.toInt() ?? 0,
        positionLeft: (json['position_left'] as num?)?.toInt() ?? 0,
        positionRight: (json['position_right'] as num?)?.toInt() ?? 0,
        confidence: (json['confidence'] as num?)?.toDouble() ?? 1,
        tags: ((json['tags'] as List?) ?? const []).map((e) => '$e').toList(),
        manuallyEdited: (json['manually_edited'] as bool?) ?? false,
      );
}

class Shelf {
  Shelf({
    required this.indexFromTop,
    required this.yRange,
    this.notch,
    this.depthCm,
    this.slope,
    this.inherited = false,
  });

  final int indexFromTop;
  final List<double> yRange;
  final int? notch;
  final double? depthCm;
  final double? slope;
  final bool inherited;

  double get top => yRange.isNotEmpty ? yRange[0] : 0;
  double get bottom => yRange.length > 1 ? yRange[1] : 0;

  factory Shelf.fromJson(Map<String, dynamic> json) => Shelf(
        indexFromTop: (json['index_from_top'] as num?)?.toInt() ?? 0,
        yRange: ((json['y_range'] as List?) ?? const [0, 0])
            .map((e) => (e as num).toDouble())
            .toList(),
        notch: (json['notch'] as num?)?.toInt(),
        depthCm: (json['depth_cm'] as num?)?.toDouble(),
        slope: (json['slope'] as num?)?.toDouble(),
        inherited: (json['inherited'] as bool?) ?? false,
      );
}

class Bay {
  Bay({
    required this.index,
    required this.xRange,
    required this.shelves,
    this.shelvesInherited = false,
  });

  final int index;
  final List<double> xRange;
  final List<Shelf> shelves;
  final bool shelvesInherited;

  double get left => xRange.isNotEmpty ? xRange[0] : 0;
  double get right => xRange.length > 1 ? xRange[1] : 0;

  factory Bay.fromJson(Map<String, dynamic> json) => Bay(
        index: (json['index'] as num?)?.toInt() ?? 0,
        xRange: ((json['x_range'] as List?) ?? const [0, 0])
            .map((e) => (e as num).toDouble())
            .toList(),
        shelves: ((json['shelves'] as List?) ?? const [])
            .map((e) => Shelf.fromJson(e as Map<String, dynamic>))
            .toList(),
        shelvesInherited: (json['shelves_inherited'] as bool?) ?? false,
      );
}

class PlanogramPage {
  PlanogramPage({
    required this.id,
    required this.number,
    this.totalPages,
    required this.size,
    required this.bays,
    required this.products,
    this.imagePath = '',
    this.warnings = const [],
    this.customerFlowReversed = false,
  });

  final String id;
  final int number;
  final int? totalPages;
  final List<double> size;
  final List<Bay> bays;
  final List<Product> products;
  String imagePath;
  final List<String> warnings;
  final bool customerFlowReversed;

  double get width => size.isNotEmpty ? size[0] : 0;
  double get height => size.length > 1 ? size[1] : 0;

  Bay? bayOf(Product product) {
    for (final bay in bays) {
      if (bay.index == product.bay) return bay;
    }
    return null;
  }

  Shelf? shelfOf(Product product) {
    final bay = bayOf(product);
    if (bay == null) return null;
    for (final shelf in bay.shelves) {
      if (shelf.indexFromTop == product.shelf) return shelf;
    }
    return null;
  }

  factory PlanogramPage.fromJson(Map<String, dynamic> json) => PlanogramPage(
        id: (json['id'] ?? '') as String,
        number: (json['number'] as num?)?.toInt() ?? 1,
        totalPages: (json['total_pages'] as num?)?.toInt(),
        size: ((json['size'] as List?) ?? const [0, 0])
            .map((e) => (e as num).toDouble())
            .toList(),
        bays: ((json['bays'] as List?) ?? const [])
            .map((e) => Bay.fromJson(e as Map<String, dynamic>))
            .toList(),
        products: ((json['products'] as List?) ?? const [])
            .map((e) => Product.fromJson(e as Map<String, dynamic>))
            .toList(),
        imagePath: (json['straightened_image'] ?? '') as String,
        warnings: ((json['warnings'] as List?) ?? const [])
            .map((e) => '$e')
            .toList(),
        customerFlowReversed:
            (json['customer_flow_reversed'] as bool?) ?? false,
      );

  Map<String, dynamic> toStoredJson() => {
        'id': id,
        'number': number,
        'total_pages': totalPages,
        'size': size,
        'straightened_image': imagePath,
        'warnings': warnings,
        'customer_flow_reversed': customerFlowReversed,
        'bays': bays
            .map((bay) => {
                  'index': bay.index,
                  'x_range': bay.xRange,
                  'shelves_inherited': bay.shelvesInherited,
                  'shelves': bay.shelves
                      .map((shelf) => {
                            'index_from_top': shelf.indexFromTop,
                            'y_range': shelf.yRange,
                            'notch': shelf.notch,
                            'depth_cm': shelf.depthCm,
                            'slope': shelf.slope,
                            'inherited': shelf.inherited,
                          })
                      .toList(),
                })
            .toList(),
        'products': products
            .map((product) => {
                  'code': product.code,
                  'name': product.name,
                  'cases': product.cases,
                  'bbox': product.bbox == null
                      ? null
                      : {
                          'x': product.bbox!.x,
                          'y': product.bbox!.y,
                          'w': product.bbox!.w,
                          'h': product.bbox!.h,
                        },
                  'image_bbox': product.imageBbox == null
                      ? null
                      : {
                          'x': product.imageBbox!.x,
                          'y': product.imageBbox!.y,
                          'w': product.imageBbox!.w,
                          'h': product.imageBbox!.h,
                        },
                  'bay': product.bay,
                  'shelf': product.shelf,
                  'position_left': product.positionLeft,
                  'position_right': product.positionRight,
                  'confidence': product.confidence,
                  'tags': product.tags,
                  'manually_edited': product.manuallyEdited,
                })
            .toList(),
      };
}

class Layout {
  Layout({
    required this.id,
    required this.name,
    required this.size,
    required this.importedAt,
    required this.pages,
  });

  final String id;
  final String name;
  final String size;
  final String importedAt;
  final List<PlanogramPage> pages;

  String get title => '$name $size'.trim();
  int get productCount =>
      pages.fold(0, (total, page) => total + page.products.length);

  factory Layout.fromJson(Map<String, dynamic> json) => Layout(
        id: (json['id'] ?? '') as String,
        name: (json['name'] ?? '') as String,
        size: (json['size'] ?? '') as String,
        importedAt: (json['imported_at'] ?? '') as String,
        pages: ((json['pages'] as List?) ?? const [])
            .map((e) => PlanogramPage.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  Map<String, dynamic> toStoredJson() => {
        'id': id,
        'name': name,
        'size': size,
        'imported_at': importedAt,
        'pages': pages.map((page) => page.toStoredJson()).toList(),
      };
}
