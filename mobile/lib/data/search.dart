/// Product code search - the same rules the desktop app uses.
library;

import 'models.dart';

const int minQueryDigits = 3;
const int maxSuggestions = 8;

enum MatchKind { nearMiss, contains, suffix, exact }

class SearchHit {
  const SearchHit({
    required this.product,
    required this.page,
    required this.layout,
    required this.kind,
    this.matchStart = 0,
    this.matchLength = 0,
    this.reason = '',
  });

  final Product product;
  final PlanogramPage page;
  final Layout layout;
  final MatchKind kind;
  final int matchStart;
  final int matchLength;
  final String reason;

  /// The code split into the part before the match, the match, and the rest,
  /// so the list can embolden exactly the digits that were typed.
  (String, String, String) highlight() {
    final code = product.code;
    if (matchLength <= 0 || matchStart < 0 || matchStart > code.length) {
      return (code, '', '');
    }
    final end = (matchStart + matchLength).clamp(0, code.length);
    return (
      code.substring(0, matchStart),
      code.substring(matchStart, end),
      code.substring(end),
    );
  }
}

class SearchResult {
  SearchResult({
    required this.query,
    required this.digits,
    this.hits = const [],
    this.suggestions = const [],
    this.tooShort = false,
  });

  final String query;
  final String digits;
  final List<SearchHit> hits;
  final List<SearchHit> suggestions;
  final bool tooShort;

  bool get isEmpty => hits.isEmpty;
  SearchHit? get single => hits.length == 1 ? hits.first : null;

  String get message {
    if (tooShort) return 'Type at least $minQueryDigits digits.';
    if (hits.isNotEmpty) {
      return '${hits.length} match${hits.length == 1 ? '' : 'es'}';
    }
    if (suggestions.isNotEmpty) {
      final codes = <String>{for (final hit in suggestions) hit.product.code};
      return 'No product ending in $digits. Did you mean ${codes.join(', ')}?';
    }
    return 'No product ending in $digits.';
  }
}

/// Keep only digits: a typed letter is almost always a misread O or l.
String normaliseCode(String text) {
  const swaps = {
    'O': '0', 'o': '0', 'Q': '0', 'D': '0',
    'I': '1', 'l': '1', 'i': '1', '|': '1',
    'Z': '2', 'z': '2', 'S': '5', 's': '5', 'B': '8',
  };
  final buffer = StringBuffer();
  for (final character in text.split('')) {
    final swapped = swaps[character] ?? character;
    if (RegExp(r'\d').hasMatch(swapped)) buffer.write(swapped);
  }
  return buffer.toString();
}

Map<String, String> nearMissVariants(String code) {
  final variants = <String, String>{};
  for (var index = 0; index < code.length; index++) {
    for (final digit in '0123456789'.split('')) {
      if (digit != code[index]) {
        final variant =
            code.substring(0, index) + digit + code.substring(index + 1);
        variants.putIfAbsent(variant, () => 'one digit different');
      }
    }
  }
  for (var index = 0; index < code.length - 1; index++) {
    if (code[index] != code[index + 1]) {
      final swapped = code.substring(0, index) +
          code[index + 1] +
          code[index] +
          code.substring(index + 2);
      variants.putIfAbsent(swapped, () => 'two digits swapped');
    }
  }
  variants.remove(code);
  return variants;
}

class _Entry {
  const _Entry(this.product, this.page, this.layout);
  final Product product;
  final PlanogramPage page;
  final Layout layout;
}

/// Everything searchable, held in memory: a few thousand rows at most.
class ProductIndex {
  ProductIndex([List<Layout> layouts = const []]) {
    rebuild(layouts);
  }

  final List<_Entry> _entries = [];

  int get length => _entries.length;

  void rebuild(List<Layout> layouts) {
    _entries.clear();
    for (final layout in layouts) {
      for (final page in layout.pages) {
        for (final product in page.products) {
          if (product.code.isNotEmpty) {
            _entries.add(_Entry(product, page, layout));
          }
        }
      }
    }
  }

  SearchResult search(String query, {String? layoutId, int limit = 50}) {
    final digits = normaliseCode(query);
    if (digits.length < minQueryDigits) {
      return SearchResult(query: query, digits: digits, tooShort: true);
    }

    final scope = layoutId == null
        ? _entries
        : _entries.where((entry) => entry.layout.id == layoutId).toList();

    final hits = <SearchHit>[];
    for (final entry in scope) {
      final code = entry.product.code;
      MatchKind kind;
      int start;
      if (code == digits) {
        kind = MatchKind.exact;
        start = 0;
      } else if (code.endsWith(digits)) {
        kind = MatchKind.suffix;
        start = code.length - digits.length;
      } else {
        start = code.indexOf(digits);
        if (start < 0) continue;
        kind = MatchKind.contains;
      }
      hits.add(SearchHit(
        product: entry.product,
        page: entry.page,
        layout: entry.layout,
        kind: kind,
        matchStart: start,
        matchLength: digits.length,
      ));
    }
    hits.sort(_compare);

    if (hits.isEmpty) {
      return SearchResult(
        query: query,
        digits: digits,
        suggestions: _suggest(digits, scope),
      );
    }
    return SearchResult(
      query: query,
      digits: digits,
      hits: hits.take(limit).toList(),
    );
  }

  int _compare(SearchHit a, SearchHit b) {
    final byKind = b.kind.index.compareTo(a.kind.index);
    if (byKind != 0) return byKind;
    final byLength = a.product.code.length.compareTo(b.product.code.length);
    if (byLength != 0) return byLength;
    final byLayout =
        a.layout.title.toLowerCase().compareTo(b.layout.title.toLowerCase());
    if (byLayout != 0) return byLayout;
    final byPage = a.page.number.compareTo(b.page.number);
    if (byPage != 0) return byPage;
    final byBay = a.product.bay.compareTo(b.product.bay);
    if (byBay != 0) return byBay;
    final byShelf = a.product.shelf.compareTo(b.product.shelf);
    if (byShelf != 0) return byShelf;
    return a.product.positionLeft.compareTo(b.product.positionLeft);
  }

  List<SearchHit> _suggest(String digits, List<_Entry> scope) {
    final variants = nearMissVariants(digits);
    if (variants.isEmpty) return const [];
    final found = <SearchHit>[];
    for (final entry in scope) {
      final code = entry.product.code;
      for (final variant in variants.entries) {
        var start = -1;
        if (code == variant.key) {
          start = 0;
        } else if (code.endsWith(variant.key)) {
          start = code.length - variant.key.length;
        } else {
          start = code.indexOf(variant.key);
        }
        if (start < 0) continue;
        found.add(SearchHit(
          product: entry.product,
          page: entry.page,
          layout: entry.layout,
          kind: MatchKind.nearMiss,
          matchStart: start,
          matchLength: variant.key.length,
          reason: variant.value,
        ));
        break;
      }
    }
    found.sort((a, b) {
      final byReason = (a.reason == 'one digit different' ? 0 : 1)
          .compareTo(b.reason == 'one digit different' ? 0 : 1);
      if (byReason != 0) return byReason;
      return a.product.code.compareTo(b.product.code);
    });
    return found.take(maxSuggestions).toList();
  }

  /// Which product was tapped on the page image.
  Product? productAt(PlanogramPage page, double x, double y) {
    Product? best;
    var bestArea = double.infinity;
    for (final product in page.products) {
      for (final box in [product.bbox, product.imageBbox]) {
        if (box == null) continue;
        if (box.contains(x, y) && box.w * box.h < bestArea) {
          best = product;
          bestArea = box.w * box.h;
        }
      }
    }
    return best;
  }
}
