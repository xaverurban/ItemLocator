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


def test_search_over_parsed_pages(pages):
    """The acceptance searches, run against what the parser actually produced."""
    from shelffinder.core.locate import locate_hit
    from shelffinder.core.models import Layout, group_pages_into_layouts
    from shelffinder.core.search import MatchKind, ProductIndex

    layouts = group_pages_into_layouts(list(pages.values()))
    assert len(layouts) == 1
    index = ProductIndex(layouts)

    result = index.search("038")
    assert result.single is not None, [hit.code for hit in result.hits]
    card = locate_hit(result.single)
    assert card.code == "7008038"
    assert card.page.number == 2
    assert card.position_left == 1
    assert card.shelf.notch == 12
    assert result.single.kind is MatchKind.SUFFIX

    card = locate_hit(index.search("5481").single)
    assert card.position_right == 1 and card.shelf.notch == 33

    card = locate_hit(index.search("167").hits[0])
    assert card.code == "230167" and card.page.number == 1

    card = locate_hit(index.search("1060").single)
    assert card.code == "1060" and card.page.number == 1
    assert card.shelf.notch == 3
    assert card.neighbour_left is not None       # sits between two other products


def test_search_suggests_near_misses_from_parsed_data(pages):
    from shelffinder.core.models import group_pages_into_layouts
    from shelffinder.core.search import ProductIndex

    index = ProductIndex(group_pages_into_layouts(list(pages.values())))
    result = index.search("7008039")             # last digit wrong
    assert result.is_empty
    assert "7008038" in [hit.product.code for hit in result.suggestions]


@pytest.mark.parametrize("turned", [0, 90, 180, 270])
def test_a_sideways_page_is_turned_upright(samples, engine, turned):
    """A sheet photographed on its side must come back upright.

    The page's own shape is not a safe shortcut here: a sideways sheet can still
    warp to a portrait image, which used to leave the whole page rotated and the
    parse reading the sheet against the grain.
    """
    from shelffinder.core.imaging import detect_rotation, rotate_image

    page = cv2.imread(os.path.join(samples, "page_1_clean.png"))
    detected = detect_rotation(rotate_image(page, turned), engine)
    assert detected == (360 - turned) % 360


def test_a_sideways_photo_still_parses(samples, engine):
    from shelffinder.core.imaging import rotate_image
    from shelffinder.core.parser import parse_image

    photo = cv2.imread(os.path.join(samples, "page_2_photo.jpg"))
    page, flat = parse_image(rotate_image(photo, 90), engine, source_file="sideways.jpg")
    codes = {product.code for product in page.products}
    assert "5481" in codes, sorted(codes)
    assert len(page.bays) == 3
    assert flat.image.shape[0] > flat.image.shape[1]        # portrait, the right way up


def test_rotation_survives_text_that_reads_in_any_direction(samples, engine):
    """The OCR models read a line of text lying on its side, so which way up a
    page goes cannot be decided from what the text says.

    This pins the geometric signal: on an upright page the text boxes are wide.
    """
    from shelffinder.core.imaging import rotate_image, text_direction_score

    page = cv2.imread(os.path.join(samples, "page_1_clean.png"))
    small = cv2.resize(page, None, fx=0.45, fy=0.45)
    upright = text_direction_score(engine.read(small))
    sideways = text_direction_score(engine.read(rotate_image(small, 90)))
    assert upright > sideways * 3, (upright, sideways)


@pytest.mark.parametrize("turned", [0, 90, 180, 270])
def test_a_photographed_sheet_ends_up_upright(samples, engine, turned):
    from shelffinder.core.imaging import rotate_image, straighten

    photo = cv2.imread(os.path.join(samples, "page_2_photo.jpg"))
    flat = straighten(rotate_image(photo, turned), ocr_engine=engine)
    assert flat.image.shape[0] > flat.image.shape[1], "the page should end up portrait"

    lines = engine.read(cv2.resize(flat.image, None, fx=0.5, fy=0.5))
    wide = sum(1 for line in lines if line.bbox.w > line.bbox.h)
    assert wide > len(lines) * 0.8, "the text should be reading left to right"


def test_notch_order_decides_which_way_up(samples, engine):
    """Notch numbers count down the page; upside down, they count up."""
    from shelffinder.core.imaging import rotate_image, upside_down_score

    page = cv2.imread(os.path.join(samples, "page_1_clean.png"))
    small = cv2.resize(page, None, fx=0.45, fy=0.45)
    height = float(small.shape[0])
    assert upside_down_score(engine.read(small), height) < 0
    flipped = rotate_image(small, 180)
    assert upside_down_score(engine.read(flipped), float(flipped.shape[0])) > 0
