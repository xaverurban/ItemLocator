/// Finding the printed rules on a sheet without OpenCV.
///
/// A bay divider is a long vertical line, so it shows up as a column of the
/// image that is far darker than its neighbours over most of the page. That is
/// enough to find the bays even on a page where only the first bay prints its
/// own "Notch:" lines.
library;

import 'dart:math' as math;

import 'package:image/image.dart' as img;

class RuleScan {
  const RuleScan(this.verticals, this.horizontals);

  /// X positions of bay dividers, in the coordinates of the image scanned.
  final List<double> verticals;

  /// Y positions of shelf rules, same coordinates.
  final List<double> horizontals;
}

/// Scan for long straight rules. Returns positions in the given image's pixels.
RuleScan scanRules(
  img.Image image, {
  int workingWidth = 900,
  double minVerticalFraction = 0.32,
  double minHorizontalFraction = 0.30,
}) {
  final scale = workingWidth / image.width;
  final small = image.width > workingWidth
      ? img.copyResize(image, width: workingWidth)
      : image;
  final width = small.width;
  final height = small.height;

  // Luminance, and a threshold that follows the page rather than a fixed value.
  final luminance = List<int>.filled(width * height, 255);
  var total = 0;
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      final pixel = small.getPixel(x, y);
      final value = img.getLuminance(pixel).round();
      luminance[y * width + x] = value;
      total += value;
    }
  }
  final mean = total / (width * height);
  final threshold = math.max(40.0, mean * 0.72);

  final columnDark = List<int>.filled(width, 0);
  final rowDark = List<int>.filled(height, 0);
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      if (luminance[y * width + x] < threshold) {
        columnDark[x] += 1;
        rowDark[y] += 1;
      }
    }
  }

  final verticals = _peaks(columnDark, (height * minVerticalFraction).round(),
      math.max(3, (width * 0.01).round()));
  final horizontals = _peaks(rowDark, (width * minHorizontalFraction).round(),
      math.max(3, (height * 0.01).round()));

  return RuleScan(
    [for (final x in verticals) x / scale],
    [for (final y in horizontals) y / scale],
  );
}

/// Runs of values above [minimum], collapsed to the middle of each run.
List<double> _peaks(List<int> counts, int minimum, int mergeWithin) {
  final found = <double>[];
  var runStart = -1;
  for (var index = 0; index < counts.length; index++) {
    final above = counts[index] >= minimum;
    if (above && runStart < 0) {
      runStart = index;
    } else if (!above && runStart >= 0) {
      found.add((runStart + index - 1) / 2);
      runStart = -1;
    }
  }
  if (runStart >= 0) found.add((runStart + counts.length - 1) / 2);

  // Two rules printed a hair apart are one rule.
  final merged = <double>[];
  for (final position in found) {
    if (merged.isNotEmpty && position - merged.last <= mergeWithin) {
      merged[merged.length - 1] = (merged.last + position) / 2;
    } else {
      merged.add(position);
    }
  }
  return merged;
}
