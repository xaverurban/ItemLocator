"""Parser internals that do not need OCR or images."""

import numpy as np
import pytest

from shelffinder.core import parser, structure
from shelffinder.core.models import BBox, Bay, Shelf
from shelffinder.core.ocr import TextLine
from shelffinder.core.textparse import NotchInfo


def line(text: str, x: float, y: float, w: float = 90.0, h: float = 14.0,
         confidence: float = 0.95) -> TextLine:
    return TextLine(text=text, bbox=BBox(x, y, w, h), confidence=confidence)


def test_group_labels_builds_code_name_cases():
    lines = [
        line("7008038", 100, 100),
        line("Fairy 654ml", 100, 118),
        line("Original", 100, 136),
        line("Cases:4", 100, 154),
        line("1023107", 300, 100),
        line("Fairy WUL Lemon", 300, 118),
        line("Cases:2", 300, 136),
    ]
    labels = parser._group_labels(lines, parser.ParseOptions())
    assert [label["code"] for label in labels] == ["7008038", "1023107"]
    assert labels[0]["name"] == "Fairy 654ml Original"
    assert labels[0]["cases"] == 4
    assert labels[1]["cases"] == 2
    # The box covers every line of the label.
    assert labels[0]["bbox"].y2 >= 168


def test_group_labels_stops_at_the_next_code():
    lines = [
        line("7008038", 100, 100),
        line("Fairy 654ml Original", 100, 118),
        line("1023107", 100, 140),          # next label, no Cases line in between
        line("Fairy WUL Lemon", 100, 158),
        line("Cases:2", 100, 176),
    ]
    labels = parser._group_labels(lines, parser.ParseOptions())
    assert [label["code"] for label in labels] == ["7008038", "1023107"]
    assert labels[0]["name"] == "Fairy 654ml Original"
    assert labels[0]["cases"] is None


def test_merge_notch_entries_folds_repeat_reads_of_one_line():
    entries = [
        (100.0, NotchInfo(33, None, None, "Notch: 33"), line("Notch: 33", 60, 94)),
        (103.0, NotchInfo(33, 62.0, 0.0, "Notch: 33 Depth:62cm Slope:0"),
         line("Notch: 33 Depth:62cm Slope:0", 62, 96, w=210)),
    ]
    merged = parser._merge_notch_entries(entries, page_height=3000)
    assert len(merged) == 1
    assert merged[0][1].complete


def test_merge_notch_entries_keeps_the_same_notch_in_other_bays():
    entries = [
        (100.0, NotchInfo(33, 62.0, 0.0, "x"), line("Notch: 33 Depth:62cm Slope:0", 60, 94, w=200)),
        (101.0, NotchInfo(33, 62.0, 0.0, "x"), line("Notch: 33 Depth:62cm Slope:0", 700, 94, w=200)),
        (102.0, NotchInfo(33, 62.0, 0.0, "x"), line("Notch: 33 Depth:62cm Slope:0", 1400, 94, w=200)),
    ]
    assert len(parser._merge_notch_entries(entries, page_height=3000)) == 3


def test_shelf_bands_label_heads_its_row():
    notches = [(100.0, NotchInfo(33), line("Notch: 33", 60, 94)),
               (500.0, NotchInfo(22), line("Notch: 22", 60, 494)),
               (900.0, NotchInfo(12), line("Notch: 12", 60, 894))]
    product_ys = [200.0, 320.0, 600.0, 1000.0]        # products sit below their notch line
    bands, heads = parser._shelf_bands(notches, rules=[], top=80.0, bottom=1200.0,
                                       product_ys=product_ys)
    assert heads is True
    assert len(bands) == 3
    assert bands[0][0] <= 100.0 and bands[0][1] == pytest.approx(300.0)
    assert bands[-1][1] == 1200.0


def test_shelf_bands_label_trails_its_row():
    notches = [(300.0, NotchInfo(33), line("Notch: 33", 60, 294)),
               (700.0, NotchInfo(22), line("Notch: 22", 60, 694))]
    product_ys = [120.0, 200.0, 450.0, 620.0]          # products sit above their notch line
    bands, heads = parser._shelf_bands(notches, rules=[], top=80.0, bottom=1200.0,
                                       product_ys=product_ys)
    assert heads is False
    assert bands[0][0] == 80.0


def test_shelf_bands_snap_to_printed_rules():
    notches = [(100.0, NotchInfo(33), line("Notch: 33", 60, 94)),
               (500.0, NotchInfo(22), line("Notch: 22", 60, 494))]
    bands, _ = parser._shelf_bands(notches, rules=[288.0], top=80.0, bottom=900.0,
                                   product_ys=[200.0, 600.0])
    assert bands[0][1] == pytest.approx(288.0)


def test_assign_positions_counts_from_both_ends():
    from shelffinder.core.models import Product
    products = [Product(code="a", name="", bbox=BBox(300, 10, 20, 20), bay=1, shelf=1),
                Product(code="b", name="", bbox=BBox(100, 10, 20, 20), bay=1, shelf=1),
                Product(code="c", name="", bbox=BBox(200, 10, 20, 20), bay=1, shelf=1),
                Product(code="d", name="", bbox=BBox(100, 90, 20, 20), bay=1, shelf=2)]
    parser._assign_positions(products)
    by_code = {p.code: (p.position_left, p.position_right) for p in products}
    assert by_code["b"] == (1, 3)
    assert by_code["c"] == (2, 2)
    assert by_code["a"] == (3, 1)
    assert by_code["d"] == (1, 1)


def test_bay_ranges_from_vertical_rules():
    grid = structure.GridLines(verticals=[60.0, 700.0, 1340.0, 1980.0],
                               bounds=(60.0, 200.0, 1980.0, 2900.0), found=True)
    ranges = structure.bay_ranges(grid, page_width=2000)
    assert len(ranges) == 3
    assert ranges[0][0] == 60.0 and ranges[-1][1] == 1980.0


def test_bay_ranges_ignore_a_stray_rule():
    grid = structure.GridLines(verticals=[60.0, 700.0, 712.0, 1980.0],
                               bounds=(60.0, 200.0, 1980.0, 2900.0), found=True)
    ranges = structure.bay_ranges(grid, page_width=2000)
    assert len(ranges) == 2


def test_horizontal_rules_in_bay_needs_coverage():
    grid = structure.GridLines(horizontals=[(400.0, 60.0, 690.0), (800.0, 600.0, 640.0)],
                               bounds=(60.0, 200.0, 1980.0, 2900.0), found=True)
    assert structure.horizontal_rules_in(grid, 60.0, 700.0) == [400.0]


def test_shelf_lookup_falls_back_to_the_nearest_shelf():
    bay = Bay(index=1, x_range=(0.0, 100.0), shelves=[
        Shelf(index_from_top=1, y_range=(0.0, 100.0)),
        Shelf(index_from_top=2, y_range=(100.0, 200.0)),
    ])
    assert parser._shelf_for(bay, 150.0).index_from_top == 2
    assert parser._shelf_for(bay, 260.0).index_from_top == 2       # just below the last band


def test_dedupe_labels_drops_repeat_reads():
    labels = [
        {"code": "7008038", "name": "Fairy 654ml Original", "cases": 4,
         "bbox": BBox(100, 100, 90, 60), "confidence": 0.95},
        {"code": "7008038", "name": "Fairy 654ml", "cases": None,
         "bbox": BBox(104, 103, 88, 58), "confidence": 0.6},
        {"code": "1023107", "name": "Fairy WUL Lemon", "cases": 2,
         "bbox": BBox(400, 100, 90, 60), "confidence": 0.9},
    ]
    kept = parser._dedupe_labels(labels)
    assert [label["code"] for label in kept] == ["7008038", "1023107"]
    assert kept[0]["cases"] == 4


def test_white_label_snapping_ignores_oversized_boxes():
    text = BBox(100, 100, 80, 50)
    label_box = BBox(96, 96, 90, 58)
    bottle = BBox(90, 40, 100, 400)
    assert parser._snap_to_label_box(text, [bottle]) is None
    assert parser._snap_to_label_box(text, [bottle, label_box]) is label_box


def test_estimate_text_height_on_drawn_text():
    import cv2
    image = np.full((200, 400, 3), 255, np.uint8)
    for index in range(4):
        cv2.putText(image, "Fairy 654ml", (10, 40 + index * 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 0, 0), 1, cv2.LINE_AA)
    height = parser._estimate_text_height(image, BBox(0, 0, 400, 200))
    assert height is not None and 5 <= height <= 25
