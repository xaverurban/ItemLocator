/// Corrections made on the phone, and what follows them.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:shelffinder_mobile/data/editing.dart';
import 'package:shelffinder_mobile/data/models.dart';

import 'helpers.dart';

PlanogramPage page() => householdLayout().pages[1];

Product find(PlanogramPage page, String code) =>
    page.products.firstWhere((product) => product.code == code);

void main() {
  test('a correction counts as checked and clears the flag', () {
    final sheet = page();
    final product = find(sheet, '7008038').copyWith(confidence: 0.3);
    sheet.products = [
      for (final other in sheet.products)
        other.code == '7008038' ? product : other,
    ];
    expect(product.needsChecking, isTrue);

    sheet.products = updateProduct(sheet, product, name: 'Fairy Original 654ml');
    final fixed = find(sheet, '7008038');
    expect(fixed.name, 'Fairy Original 654ml');
    expect(fixed.manuallyEdited, isTrue);
    expect(fixed.confidence, 1);
    expect(fixed.needsChecking, isFalse);
  });

  test('a code keeps only its digits', () {
    final sheet = page();
    sheet.products = updateProduct(sheet, find(sheet, '5481'), code: ' 70 08 038 ');
    expect(find(sheet, '7008038').code, '7008038');
  });

  test('cases can be cleared as well as set', () {
    final sheet = page();
    sheet.products = updateProduct(sheet, find(sheet, '5481'), cases: 9);
    expect(find(sheet, '5481').cases, 9);

    sheet.products =
        updateProduct(sheet, find(sheet, '5481'), clearCases: true);
    expect(find(sheet, '5481').cases, isNull);
  });

  test('removing a product renumbers its shelf', () {
    final sheet = page();
    final lemon = find(sheet, '1023107');       // position 2 of 4
    sheet.products = deleteProduct(sheet, lemon);

    expect(sheet.products.any((product) => product.code == '1023107'), isFalse);
    expect(find(sheet, '7008038').positionLeft, 1);
    expect(find(sheet, '7190489').positionLeft, 2);
    expect(find(sheet, '10076121').positionRight, 1);
  });

  test('the summary points at what to check', () {
    final sheet = page();
    sheet.products = [
      for (final product in sheet.products)
        product.code == '5481' ? product.copyWith(name: '') : product,
    ];
    final summary = reviewSummary(sheet);

    expect(summary.total, sheet.products.length);
    expect(summary.missingName, 1);
    expect(summary.needsChecking, greaterThanOrEqualTo(1));
    expect(summary.baysSharingShelves, [2, 3]);
    expect(summary.isClean, isFalse);
    expect(summary.describe(), contains('to check'));
  });

  test('what to check comes back worst first', () {
    final layout = householdLayout();
    final sheet = layout.pages[1];
    sheet.products = [
      for (final product in sheet.products)
        if (product.code == '5481')
          product.copyWith(confidence: 0.2)
        else if (product.code == '200593')
          product.copyWith(confidence: 0.5)
        else
          product,
    ];

    final pending = productsToCheck(layout);
    expect(pending.length, greaterThanOrEqualTo(2));
    expect(pending.first.$2.code, '5481');      // least confident first
  });

  test('a product checked by hand is not flagged again', () {
    final sheet = page();
    final product = find(sheet, '5481').copyWith(confidence: 0.1);
    expect(product.needsChecking, isTrue);
    expect(product.copyWith(manuallyEdited: true).needsChecking, isFalse);
  });
}
