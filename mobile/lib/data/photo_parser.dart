/// Turning a photographed sheet into a page, using only what OCR gives us.
///
/// The desktop app has OpenCV: it finds the paper, flattens it and detects the
/// printed rules. The phone has none of that, so this works from the text alone
/// - which the sheets make possible, because every shelf announces itself with
/// a "Notch:" line and every product carries a code and a "Cases:" line.
library;

import 'dart:math' as math;

import 'models.dart';
import 'textparse.dart' as rules;

/// One line of text as the OCR engine saw it, in image pixels.
class OcrLine {
  const OcrLine(this.text, this.bbox, {this.confidence = 1});

  final String text;
  final BBox bbox;
  final double confidence;
}

class PhotoParseResult {
  PhotoParseResult({
    required this.page,
    required this.layoutName,
    required this.layoutSize,
    required this.warnings,
  });

  final PlanogramPage page;
  final String layoutName;
  final String layoutSize;
  final List<String> warnings;
}

/// How much this reading looks like upright text rather than text on its side.
double textDirectionScore(List<OcrLine> lines) {
  if (lines.isEmpty) return 0;
  var wide = 0.0;
  var weight = 0.0;
  for (final line in lines) {
    weight += line.confidence;
    if (line.bbox.w > line.bbox.h) wide += line.confidence;
  }
  if (weight <= 0) return 0;
  return (wide / weight) * math.log(1 + lines.length);
}

/// Positive when the page looks upside down: notch numbers count *down* a page.
double upsideDownScore(List<OcrLine> lines, double pageHeight) {
  var score = 0.0;
  final notches = <(double, int)>[];
  for (final line in lines) {
    final info = rules.notchOf(line.text);
    if (info != null) notches.add((line.bbox.centreY, info.notch));
  }
  if (notches.length >= 3) {
    var agree = 0;
    var disagree = 0;
    for (var i = 0; i < notches.length; i++) {
      for (var j = i + 1; j < notches.length; j++) {
        final (yA, notchA) = notches[i];
        final (yB, notchB) = notches[j];
        if ((yA - yB).abs() < pageHeight * 0.02 || notchA == notchB) continue;
        if ((yA > yB) == (notchA < notchB)) {
          agree++;
        } else {
          disagree++;
        }
      }
    }
    if (agree + disagree >= 3) {
      score += 6.0 * (disagree - agree) / (agree + disagree);
    }
  }

  for (final line in lines) {
    final text = line.text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
    final nearTop = line.bbox.centreY < pageHeight * 0.18;
    final nearBottom = line.bbox.centreY > pageHeight * 0.82;
    if (rules.pageNumberOf(line.text) != null && text.length <= 12) {
      score += nearTop ? 1.5 : (nearBottom ? -1.5 : 0.0);
    }
    if (text.contains('customer') && text.contains('flow')) {
      score += nearTop ? 2.0 : (nearBottom ? -2.0 : 0.0);
    }
    if (text.replaceAll(' ', '').contains('layoutmanagement')) {
      score += nearBottom ? 1.5 : (nearTop ? -1.5 : 0.0);
    }
    if (text.contains('visible notch') || text.contains('plinth')) {
      score += nearTop ? 1.5 : (nearBottom ? -1.5 : 0.0);
    }
  }
  return score;
}

class _Label {
  _Label(this.code, this.name, this.cases, this.bbox, this.confidence);
  final String code;
  final String name;
  final int? cases;
  final BBox bbox;
  final double confidence;
}

/// Group lines into labels: a code, the name wrapped over a few lines, Cases:N.
List<_Label> _groupLabels(List<OcrLine> lines) {
  final ordered = [...lines]..sort((a, b) {
      final byY = a.bbox.y.compareTo(b.bbox.y);
      return byY != 0 ? byY : a.bbox.x.compareTo(b.bbox.x);
    });

  final used = <int>{};
  final labels = <_Label>[];
  for (var index = 0; index < ordered.length; index++) {
    if (used.contains(index)) continue;
    final code = rules.codeCandidate(ordered[index].text);
    if (code == null) continue;

    final anchor = ordered[index];
    final members = <int>[index];
    final nameParts = <String>[];
    int? cases;
    var current = anchor;

    for (var follow = index + 1; follow < ordered.length; follow++) {
      if (used.contains(follow)) continue;
      final candidate = ordered[follow];
      final gap = candidate.bbox.y - current.bbox.bottom;
      final lineHeight =
          math.max(math.max(current.bbox.h, candidate.bbox.h), 6.0);
      if (gap > lineHeight * 1.9) break;
      if (candidate.bbox.y < current.bbox.y - lineHeight) continue;

      final overlap = math.min(anchor.bbox.right, candidate.bbox.right) -
          math.max(anchor.bbox.x, candidate.bbox.x);
      final narrower = math.min(anchor.bbox.w, candidate.bbox.w);
      if (overlap < narrower * 0.35 &&
          (candidate.bbox.x - anchor.bbox.x).abs() > lineHeight * 0.55) {
        continue;
      }
      if (rules.notchOf(candidate.text) != null || rules.isNoise(candidate.text)) {
        break;
      }
      if (rules.codeCandidate(candidate.text) != null) break;

      members.add(follow);
      current = candidate;
      final found = rules.casesOf(candidate.text);
      if (found != null) {
        cases = found;
        break;
      }
      nameParts.add(candidate.text);
      if (members.length >= 6) break;
    }

    used.addAll(members);
    var box = ordered[members.first].bbox;
    var confidence = 1.0;
    for (final member in members) {
      final other = ordered[member].bbox;
      box = BBox(
        math.min(box.x, other.x),
        math.min(box.y, other.y),
        math.max(box.right, other.right) - math.min(box.x, other.x),
        math.max(box.bottom, other.bottom) - math.min(box.y, other.y),
      );
      confidence = math.min(confidence, ordered[member].confidence);
    }
    labels.add(_Label(code, rules.cleanName(nameParts), cases, box, confidence));
  }
  return labels;
}

/// Build a page out of recognised text.
///
/// Bays come from where the notch lines sit across the sheet: every bay that
/// prints its own shelves puts them down its left edge. A bay with no notch
/// line of its own shares the shelves of the bay to its left, exactly as the
/// printed sheet expects a reader to.
PhotoParseResult parsePhotoText(
  List<OcrLine> lines, {
  required double width,
  required double height,
  String pageId = '',
  List<double> verticalRules = const [],
}) {
  final warnings = <String>[];

  final headerBand = height * 0.10;
  final footerBand = height * 0.90;
  final headerLines =
      lines.where((line) => line.bbox.centreY < headerBand).toList();

  var layoutName = '';
  var layoutSize = '';
  if (headerLines.isNotEmpty) {
    final title = headerLines.reduce((a, b) => a.bbox.h >= b.bbox.h ? a : b);
    final (name, size) = rules.headerOf(title.text);
    layoutName = name;
    layoutSize = size;
  }

  var number = 1;
  int? totalPages;
  for (final line in lines) {
    final found = rules.pageNumberOf(line.text);
    if (found != null &&
        (line.bbox.centreY > footerBand || line.bbox.centreY < headerBand)) {
      number = found.$1;
      totalPages = found.$2;
      break;
    }
  }

  final notchLines = <(OcrLine, rules.NotchInfo)>[];
  final content = <OcrLine>[];
  for (final line in lines) {
    if (rules.isNoise(line.text)) continue;
    final info = rules.notchOf(line.text);
    if (info != null) {
      notchLines.add((line, info));
    } else if (line.bbox.centreY >= headerBand && line.bbox.centreY <= footerBand) {
      content.add(line);
    }
  }

  final labels = _groupLabels(content);
  if (labels.isEmpty) {
    warnings.add('No product labels could be read on this photo. Try again with '
        'the whole sheet in frame, square on and in good light.');
  }
  if (notchLines.isEmpty) {
    warnings.add('No "Notch:" lines could be read, so shelves are a guess. '
        'Check before trusting the shelf numbers.');
  }

  // Bays come from the printed dividers when the scan found them - a page
  // where only the first bay prints its notch lines still has its bay lines.
  final anchorTolerance = width * 0.06;
  final bayEdges = <double>[];
  final inner = verticalRules
      .where((x) => x > width * 0.04 && x < width * 0.96)
      .toList()
    ..sort();
  if (inner.isNotEmpty) {
    bayEdges.add(0);
    for (final x in inner) {
      if (x - bayEdges.last >= width * 0.08) bayEdges.add(x);
    }
    bayEdges.add(width);
  } else {
    // Otherwise fall back to where the notch lines start across the page.
    final bayAnchors = <double>[];
    for (final (line, _) in [...notchLines]
      ..sort((a, b) => a.$1.bbox.x.compareTo(b.$1.bbox.x))) {
      final x = line.bbox.x;
      if (bayAnchors.isEmpty || (x - bayAnchors.last).abs() > anchorTolerance) {
        bayAnchors.add(x);
      }
    }
    if (bayAnchors.isEmpty) bayAnchors.add(0);
    bayEdges.add(0);
    for (var index = 1; index < bayAnchors.length; index++) {
      bayEdges.add((bayAnchors[index - 1] + bayAnchors[index]) / 2);
    }
    bayEdges.add(width);
    if (bayAnchors.length == 1 && labels.isNotEmpty) {
      warnings.add('Only one bay divider could be made out, so everything is on '
          'bay 1. Re-shoot with the whole sheet in frame if that looks wrong.');
    }
  }
  final bayCount = bayEdges.length - 1;

  final bays = <Bay>[];
  for (var index = 0; index < bayCount; index++) {
    final left = bayEdges[index];
    final right = bayEdges[index + 1];
    final own = notchLines
        .where((entry) =>
            entry.$1.bbox.x >= left - anchorTolerance &&
            entry.$1.bbox.x < right)
        .toList()
      ..sort((a, b) => a.$1.bbox.centreY.compareTo(b.$1.bbox.centreY));

    final shelves = <Shelf>[];
    for (var shelfIndex = 0; shelfIndex < own.length; shelfIndex++) {
      final top = shelfIndex == 0
          ? math.max(0.0, own[shelfIndex].$1.bbox.y - 8)
          : (own[shelfIndex - 1].$1.bbox.centreY + own[shelfIndex].$1.bbox.centreY) / 2;
      final bottom = shelfIndex == own.length - 1
          ? height
          : (own[shelfIndex].$1.bbox.centreY + own[shelfIndex + 1].$1.bbox.centreY) / 2;
      final info = own[shelfIndex].$2;
      shelves.add(Shelf(
        indexFromTop: shelfIndex + 1,
        yRange: [top, bottom],
        notch: info.notch,
        depthCm: info.depthCm,
        slope: info.slope,
      ));
    }
    bays.add(Bay(
      index: index + 1,
      xRange: [left, right],
      shelves: shelves,
    ));
  }

  // A bay with no notch line of its own borrows the one to its left.
  for (var index = 0; index < bays.length; index++) {
    if (bays[index].shelves.isNotEmpty) continue;
    for (var before = index - 1; before >= 0; before--) {
      if (bays[before].shelves.isEmpty) continue;
      bays[index] = Bay(
        index: bays[index].index,
        xRange: bays[index].xRange,
        shelvesInherited: true,
        shelves: [
          for (final shelf in bays[before].shelves)
            Shelf(
              indexFromTop: shelf.indexFromTop,
              yRange: shelf.yRange,
              notch: shelf.notch,
              depthCm: shelf.depthCm,
              slope: shelf.slope,
              inherited: true,
            ),
        ],
      );
      warnings.add('Bay ${index + 1} has no notch line of its own, so it uses '
          'bay ${before + 1}\'s shelves.');
      break;
    }
  }

  // Place every label in a bay and on a shelf.
  final products = <Product>[];
  for (final label in labels) {
    var bayIndex = 0;
    for (final bay in bays) {
      if (label.bbox.centreX >= bay.left && label.bbox.centreX <= bay.right) {
        bayIndex = bay.index;
        break;
      }
    }
    if (bayIndex == 0 && bays.isNotEmpty) bayIndex = bays.first.index;

    var shelfIndex = 0;
    final bay = bays.where((bay) => bay.index == bayIndex).firstOrNull;
    if (bay != null) {
      for (final shelf in bay.shelves) {
        if (label.bbox.centreY >= shelf.top && label.bbox.centreY <= shelf.bottom) {
          shelfIndex = shelf.indexFromTop;
          break;
        }
      }
      if (shelfIndex == 0 && bay.shelves.isNotEmpty) {
        // Nearest shelf, so a label just outside a band is still placed.
        var best = bay.shelves.first;
        var bestDistance = double.infinity;
        for (final shelf in bay.shelves) {
          final distance = math.min((shelf.top - label.bbox.centreY).abs(),
              (shelf.bottom - label.bbox.centreY).abs());
          if (distance < bestDistance) {
            best = shelf;
            bestDistance = distance;
          }
        }
        shelfIndex = best.indexFromTop;
      }
    }

    products.add(Product(
      code: label.code,
      name: label.name,
      cases: label.cases,
      bbox: label.bbox,
      bay: bayIndex,
      shelf: shelfIndex,
      confidence: label.confidence * 0.9, // read on a phone: trust it a little less
      tags: const ['phone-import'],
    ));
  }

  // Positions along each shelf, left to right.
  final grouped = <String, List<Product>>{};
  for (final product in products) {
    grouped.putIfAbsent('${product.bay}:${product.shelf}', () => []).add(product);
  }
  final placed = <Product>[];
  for (final group in grouped.values) {
    group.sort((a, b) => (a.bbox?.centreX ?? 0).compareTo(b.bbox?.centreX ?? 0));
    for (var index = 0; index < group.length; index++) {
      final product = group[index];
      placed.add(Product(
        code: product.code,
        name: product.name,
        cases: product.cases,
        bbox: product.bbox,
        imageBbox: product.imageBbox,
        bay: product.bay,
        shelf: product.shelf,
        positionLeft: index + 1,
        positionRight: group.length - index,
        confidence: product.confidence,
        tags: product.tags,
      ));
    }
  }

  final page = PlanogramPage(
    id: pageId,
    number: number,
    totalPages: totalPages,
    size: [width, height],
    bays: bays,
    products: placed,
    warnings: warnings,
  );
  return PhotoParseResult(
    page: page,
    layoutName: layoutName,
    layoutSize: layoutSize,
    warnings: warnings,
  );
}
