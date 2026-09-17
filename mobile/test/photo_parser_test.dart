/// The on-phone parser, fed the kind of text OCR returns from a real sheet.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:shelffinder_mobile/data/models.dart';
import 'package:shelffinder_mobile/data/photo_parser.dart';
import 'package:shelffinder_mobile/data/textparse.dart' as rules;

const double pageWidth = 2100;
const double pageHeight = 3000;

OcrLine line(String text, double x, double y, {double w = 260, double h = 34}) =>
    OcrLine(text, BBox(x, y, w, h));

/// Page 2 of the household sheet: three bays, only bay 1 prints its notches.
List<OcrLine> samplePage() => [
      line('IE Household 4.5m', 780, 60, w: 520, h: 54),
      line('Contact layoutmanagement@lidl.ie with any queries/suggestions', 620, 130),
      // bay 1 announces every shelf
      line('Notch: 33 Depth:62cm Slope:0', 70, 300),
      line('Notch: 22 Depth:62cm Slope:0', 70, 1000),
      line('Notch: 12 Depth:62cm Slope:0', 70, 1700),
      line('Notch: 3 Depth:80cm Slope:0', 70, 2400),
      // shelf 1, bay 1
      line('250810', 150, 420, w: 130),
      line('The Pink Stuff Miracle', 150, 460, w: 220),
      line('Paste', 150, 500, w: 90),
      line('Cases:2', 150, 540, w: 110),
      line('217970', 460, 420, w: 130),
      line('Furniture Polish Beeswax', 460, 460, w: 240),
      line('Cases:2', 460, 500, w: 110),
      // shelf 1, bay 2 and 3 (no notch lines of their own)
      line('213350', 900, 420, w: 130),
      line('Platinum Dishwasher Tabs 40WL', 900, 460, w: 280),
      line('Cases:4', 900, 500, w: 110),
      line('5481', 1600, 420, w: 100),
      line('Finish Quantum Ultimate', 1600, 460, w: 240),
      line('Cases:2', 1600, 500, w: 110),
      // shelf 3, bay 1
      line('7008038', 150, 1820, w: 150),
      line('Fairy 654ml Original', 150, 1860, w: 220),
      line('Cases:4', 150, 1900, w: 110),
      line('1023107', 430, 1820, w: 150),
      line('Fairy WUL Lemon', 430, 1860, w: 200),
      line('Cases:2', 430, 1900, w: 110),
      // footer
      line('Customer Flow', 950, 2820, w: 220),
      line('2 of 2', 1900, 2900, w: 110),
    ];

void main() {
  test('the header and page number are read', () {
    final result = parsePhotoText(samplePage(),
        width: pageWidth, height: pageHeight, pageId: 'p1');
    expect(result.layoutName, 'IE Household');
    expect(result.layoutSize, '4.5m');
    expect(result.page.number, 2);
    expect(result.page.totalPages, 2);
  });

  test('labels become products with code, name and cases', () {
    final page = parsePhotoText(samplePage(),
            width: pageWidth, height: pageHeight, pageId: 'p1')
        .page;
    final fairy =
        page.products.firstWhere((product) => product.code == '7008038');
    expect(fairy.name, 'Fairy 654ml Original');
    expect(fairy.cases, 4);
    expect(page.products.map((product) => product.code), contains('5481'));
    expect(page.products.length, 6);
  });

  test('shelves come from the notch lines', () {
    final page = parsePhotoText(samplePage(),
            width: pageWidth, height: pageHeight, pageId: 'p1')
        .page;
    final notches = page.bays.first.shelves.map((shelf) => shelf.notch).toList();
    expect(notches, [33, 22, 12, 3]);
    expect(page.bays.first.shelves.first.depthCm, 62);
    expect(page.bays.first.shelves.last.depthCm, 80);
  });

  test('a bay with no notch line of its own borrows the one to its left', () {
    // Page 2 of the real sheet prints notch lines in bay 1 only, so the bay
    // dividers have to come from the printed rules.
    final result = parsePhotoText(samplePage(),
        width: pageWidth, height: pageHeight, pageId: 'p1',
        verticalRules: const [700, 1400]);
    final page = result.page;
    expect(page.bays.length, 3);
    expect(page.bays.first.shelvesInherited, isFalse);
    expect(page.bays.skip(1).every((bay) => bay.shelvesInherited), isTrue);
    expect(result.warnings.any((note) => note.contains('no notch line')), isTrue);

    // And the products land in the bay they are printed in.
    final finish = page.products.firstWhere((product) => product.code == '5481');
    expect(finish.bay, 3);
    final platinum = page.products.firstWhere((product) => product.code == '213350');
    expect(platinum.bay, 2);
  });

  test('with no dividers found everything falls into one bay, and it says so', () {
    final result = parsePhotoText(samplePage(),
        width: pageWidth, height: pageHeight, pageId: 'p1');
    expect(result.page.bays.length, 1);
    expect(result.warnings.any((note) => note.contains('one bay divider')), isTrue);
  });

  test('products land on the right shelf and are numbered along it', () {
    final page = parsePhotoText(samplePage(),
            width: pageWidth, height: pageHeight, pageId: 'p1')
        .page;
    final fairy = page.products.firstWhere((p) => p.code == '7008038');
    expect(fairy.shelf, 3);
    expect(fairy.positionLeft, 1);

    final lemon = page.products.firstWhere((p) => p.code == '1023107');
    expect(lemon.shelf, 3);
    expect(lemon.positionLeft, 2);
    expect(lemon.positionRight, 1);

    final pinkStuff = page.products.firstWhere((p) => p.code == '250810');
    expect(pinkStuff.shelf, 1);
    expect(pinkStuff.bay, 1);
  });

  test('a phone-read product is marked as such and trusted a little less', () {
    final page = parsePhotoText(samplePage(),
            width: pageWidth, height: pageHeight, pageId: 'p1')
        .page;
    expect(page.products.first.tags, contains('phone-import'));
    expect(page.products.first.confidence, lessThan(1.0));
  });

  test('the footer note is not mistaken for a shelf', () {
    final lines = [
      ...samplePage(),
      line('Ambient Layouts: First visible notch above the plinth is notch 4.',
          70, 2860, w: 900),
    ];
    final page =
        parsePhotoText(lines, width: pageWidth, height: pageHeight, pageId: 'p1')
            .page;
    expect(page.bays.first.shelves.map((shelf) => shelf.notch), [33, 22, 12, 3]);
  });

  test('a photo with nothing readable says so instead of pretending', () {
    final result = parsePhotoText([line('~~~', 10, 10)],
        width: pageWidth, height: pageHeight, pageId: 'p1');
    expect(result.page.products, isEmpty);
    expect(result.warnings.any((note) => note.contains('No product labels')), isTrue);
    expect(result.warnings.any((note) => note.contains('Notch')), isTrue);
  });

  group('which way up', () {
    test('upright text scores far above text on its side', () {
      final upright = samplePage();
      final sideways = [
        for (final entry in upright)
          OcrLine(entry.text,
              BBox(entry.bbox.y, entry.bbox.x, entry.bbox.h, entry.bbox.w))
      ];
      expect(textDirectionScore(upright), greaterThan(textDirectionScore(sideways) * 3));
    });

    test('notch numbers counting up the page mean it is upside down', () {
      final upright = samplePage();
      expect(upsideDownScore(upright, pageHeight), lessThan(0));

      final flipped = [
        for (final entry in upright)
          OcrLine(
            entry.text,
            BBox(pageWidth - entry.bbox.right, pageHeight - entry.bbox.bottom,
                entry.bbox.w, entry.bbox.h),
          )
      ];
      expect(upsideDownScore(flipped, pageHeight), greaterThan(0));
    });
  });

  group('text rules', () {
    test('notch lines survive OCR mangling', () {
      expect(rules.notchOf('Notch:33Depth:62cmSlope:0')?.notch, 33);
      expect(rules.notchOf('N0tch: 22 Depth 62cm')?.depthCm, 62);
      expect(rules.notchOf('Notch:19Denth:62cmSlope:Q')?.slope, 0);
      expect(rules.notchOf('above the plinth is notch 4'), isNull);
    });

    test('codes are digits, whatever letters OCR saw', () {
      expect(rules.codeCandidate('7OO8O38'), '7008038');
      expect(rules.codeCandidate('l0176277'), '10176277');
      expect(rules.codeCandidate('Glass'), isNull);
      expect(rules.codeCandidate('Cases:4'), isNull);
    });

    test('cases and page numbers', () {
      expect(rules.casesOf('Cases:4'), 4);
      expect(rules.casesOf('Ca5es 8'), 8);
      expect(rules.pageNumberOf('1 of 2'), (1, 2));
      expect(rules.pageNumberOf('3 of 2'), isNull);
    });
  });
}
