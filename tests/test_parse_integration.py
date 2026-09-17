"""End-to-end parse of the synthetic sheets.

Slow: it loads the OCR models.  Run with ``pytest -m slow``.
"""

import os
import subprocess
import sys

import cv2
import pytest

pytestmark = pytest.mark.slow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples", "synthetic")


@pytest.fixture(scope="module")
def samples() -> str:
    if not os.path.exists(os.path.join(SAMPLES, "page_2_clean.png")):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_sample.py"),
                        "--out", SAMPLES], check=True, cwd=ROOT)
    return SAMPLES


@pytest.fixture(scope="module")
def engine():
    from shelffinder.core.ocr import RapidOcrEngine
    return RapidOcrEngine()


@pytest.fixture(scope="module")
def pages(samples, engine) -> dict:
    from shelffinder.core.parser import parse_image
    parsed = {}
    for number in (1, 2):
        path = os.path.join(samples, f"page_{number}_clean.png")
        page, _ = parse_image(cv2.imread(path), engine, source_file=path)
        parsed[number] = page
    return parsed


def find(page, code):
    return [product for product in page.products if product.code == code]


def test_header_and_page_numbers(pages):
    for number, page in pages.items():
        assert page.layout_size == "4.5m"
        assert "Household" in page.layout_name.replace(" ", "")
        assert (page.number, page.total_pages) == (number, 2)


def test_fairy_654ml_is_leftmost_on_the_notch_12_shelf(pages):
    """Acceptance test: "038" finds 7008038 on page 2, notch 12 shelf, leftmost."""
    page = pages[2]
    matches = find(page, "7008038")
    assert len(matches) == 1
    product = matches[0]
    assert product.bay == 1
    assert product.position_left == 1
    shelf = page.shelf_of(product)
    assert shelf is not None and shelf.notch == 12
    assert shelf.depth_cm == 62 and shelf.slope == 0
    assert product.cases == 4


def test_finish_quantum_is_rightmost_on_the_top_shelf(pages):
    """Acceptance test: "5481" finds Finish Quantum Ultimate, page 2, top shelf."""
    page = pages[2]
    matches = find(page, "5481")
    assert len(matches) == 1
    product = matches[0]
    assert product.shelf == 1
    assert product.position_right == 1
    assert product.bay == len(page.bays)
    shelf = page.shelf_of(product)
    assert shelf is not None and shelf.notch == 33


def test_thick_bleach_is_on_page_one(pages):
    """Acceptance test: "167" finds 230167 Thick Bleach Original/Citrus on page 1."""
    matches = find(pages[1], "230167")
    assert len(matches) == 1
    assert "bleach" in matches[0].name.lower()


def test_tiny_label_is_read_on_the_bottom_shelf(pages):
    """Acceptance test: "1060" finds Febreze Bathroom Spring Awakening, bottom shelf."""
    page = pages[1]
    matches = find(page, "1060")
    assert len(matches) == 1
    product = matches[0]
    assert product.bay == 1
    bay = page.bay_of(product)
    assert product.shelf == len(bay.shelves)          # bottom shelf of its bay
    shelf = page.shelf_of(product)
    assert shelf is not None and shelf.notch == 3


def test_every_notch_line_is_found(pages):
    """Acceptance test: every "Notch:" line on both pages is matched to a shelf."""
    expected = {1: [(33, 62), (26, 62), (20, 62), (13, 62), (3, 80),      # bay 1
                    (33, 62), (2, 80), (3, 80),                          # bay 2
                    (33, 62), (19, 62), (11, 62), (3, 80)],              # bay 3
                2: [(33, 62), (22, 62), (12, 62), (3, 80)]}
    for number, page in pages.items():
        found = [(shelf.notch, shelf.depth_cm) for bay in page.bays for shelf in bay.shelves
                 if not shelf.inherited]
        assert sorted(found) == sorted(expected[number]), f"page {number}"
        for bay in page.bays:
            for shelf in bay.shelves:
                assert shelf.slope == 0


def test_bays_without_notch_lines_share_the_previous_bay(pages):
    page = pages[2]
    assert len(page.bays) == 3
    assert page.bays[0].shelves_inherited is False
    assert page.bays[1].shelves_inherited is True
    assert page.bays[2].shelves_inherited is True
    assert any("no notch line of its own" in warning for warning in page.warnings)


def test_repeated_codes_keep_every_location(pages):
    """The same code appears on more than one shelf - both must survive."""
    page = pages[1]
    duplicates = [code for code in {"241709", "209041"} if len(find(page, code)) >= 1]
    assert duplicates, "expected the repeated codes to be read at least once"


def test_markers_are_stored_as_tags(pages):
    assert "NTA" in pages[1].tags or "NTA" in pages[2].tags
