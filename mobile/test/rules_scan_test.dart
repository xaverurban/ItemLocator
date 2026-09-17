/// Finding printed rules in an image, without OpenCV.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:shelffinder_mobile/data/rules_scan.dart';

img.Image drawSheet() {
  final sheet = img.Image(width: 1200, height: 1600);
  img.fill(sheet, color: img.ColorRgb8(255, 255, 255));
  final ink = img.ColorRgb8(20, 20, 20);

  // Two bay dividers and three shelf rules, as a planogram prints them.
  for (final x in [400, 800]) {
    img.fillRect(sheet, x1: x - 1, y1: 120, x2: x + 1, y2: 1500, color: ink);
  }
  for (final y in [120, 600, 1080, 1500]) {
    img.fillRect(sheet, x1: 40, y1: y - 1, x2: 1160, y2: y + 1, color: ink);
  }
  // Some text-like noise that must not be mistaken for a rule.
  for (var index = 0; index < 40; index++) {
    img.fillRect(sheet,
        x1: 80 + (index % 8) * 120,
        y1: 200 + (index ~/ 8) * 180,
        x2: 80 + (index % 8) * 120 + 60,
        y2: 200 + (index ~/ 8) * 180 + 14,
        color: ink);
  }
  return sheet;
}

void main() {
  test('bay dividers and shelf rules are found where they were drawn', () {
    final scan = scanRules(drawSheet());

    bool near(List<double> found, double wanted) =>
        found.any((value) => (value - wanted).abs() < 18);

    expect(near(scan.verticals, 400), isTrue, reason: '\${scan.verticals}');
    expect(near(scan.verticals, 800), isTrue, reason: '\${scan.verticals}');
    expect(scan.verticals.length, lessThanOrEqualTo(4));

    expect(near(scan.horizontals, 120), isTrue, reason: '\${scan.horizontals}');
    expect(near(scan.horizontals, 1500), isTrue, reason: '\${scan.horizontals}');
  });

  test('a blank page has no rules to find', () {
    final blank = img.Image(width: 600, height: 800);
    img.fill(blank, color: img.ColorRgb8(255, 255, 255));
    final scan = scanRules(blank);
    expect(scan.verticals, isEmpty);
    expect(scan.horizontals, isEmpty);
  });
}
