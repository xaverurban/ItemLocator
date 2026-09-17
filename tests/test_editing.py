"""Corrections to a parsed page, and the bookkeeping that follows them."""

import pytest

from shelffinder.core import editing
from shelffinder.core.models import BBox, Page, Product


def find(page: Page, code: str) -> Product:
    return next(product for product in page.products if product.code == code)


@pytest.fixture
def page(household_layout) -> Page:
    return household_layout.pages[1]          # page 2: three bays, four shelves


def test_fixing_a_code_marks_it_checked(page):
    product = find(page, "7008038")
    product.confidence = 0.4
    product.tags.append("unreadable")

    editing.update_product(page, product, code="7008039")
    assert product.code == "7008039"
    assert product.manually_edited is True
    assert product.confidence == 1.0
    assert "unreadable" not in product.tags


def test_a_code_keeps_only_its_digits(page):
    product = find(page, "5481")
    editing.update_product(page, product, code=" 70 08 O38 ")
    assert product.code == "700838"


def test_moving_a_box_moves_the_product_to_the_right_shelf(page):
    product = find(page, "7008038")           # bay 1, shelf 3
    assert (product.bay, product.shelf) == (1, 3)

    shelf_one = page.bays[0].shelves[0]
    editing.update_product(page, product,
                           bbox=BBox(150, shelf_one.y_range[0] + 20, 120, 90))
    assert product.shelf == 1
    assert product.bay == 1


def test_moving_a_box_across_a_bay_line_renumbers_both_shelves(page):
    product = find(page, "7008038")           # bay 1 shelf 3, position 1 of 4
    bay_two = page.bays[1]
    shelf = bay_two.shelves[2]

    editing.update_product(page, product,
                           bbox=BBox(bay_two.x_range[0] + 40, shelf.y_range[0] + 30, 120, 90))
    assert product.bay == 2
    assert product.shelf == 3

    # The shelf it left renumbers, and the one it joined makes room.
    lemon = find(page, "1023107")
    assert lemon.position_left == 1
    assert product.position_left == 1         # it landed to the left of the salt
    assert find(page, "200593").position_left == 2


def test_adding_a_product_places_and_numbers_it(page):
    bay = page.bays[0]
    shelf = bay.shelves[2]
    added = editing.add_product(page, BBox(bay.x_range[0] + 5, shelf.y_range[0] + 10, 100, 80),
                                code="9999001", name="Added by hand", cases=6)

    assert added.bay == 1 and added.shelf == 3
    assert added.position_left == 1           # furthest left on that shelf
    assert find(page, "7008038").position_left == 2
    assert added.manually_edited is True
    assert "added-by-hand" in added.tags


def test_deleting_a_product_renumbers_the_shelf(page):
    lemon = find(page, "1023107")             # bay 1 shelf 3, position 2 of 4
    assert editing.delete_product(page, lemon) is True
    assert all(product.code != "1023107" for product in page.products)

    assert find(page, "7008038").position_left == 1
    assert find(page, "7190489").position_left == 2
    assert find(page, "10076121").position_right == 1


def test_deleting_something_that_is_not_there_says_so(page):
    assert editing.delete_product(page, Product(code="nope", name="")) is False


def test_moving_a_bay_line_moves_the_products_with_it(page):
    original = [bay.x_range for bay in page.bays]
    # Drag the first divider right, past the Fairy labels.
    editing.set_bay_edges(page, [0, 900, original[1][1], original[2][1]])

    assert len(page.bays) == 3
    assert page.bays[0].x_range == (0, 900)
    assert find(page, "200593").bay == 1       # was bay 2, the line moved past it
    assert find(page, "7175141").bay == 2       # sits at 1360, inside the new bay 2
    assert find(page, "5481").bay == 3


def test_a_redrawn_bay_keeps_the_shelves_it_had(page):
    notches = [shelf.notch for shelf in page.bays[0].shelves]
    editing.set_bay_edges(page, [0, 700, 1400, 2100])
    assert [shelf.notch for shelf in page.bays[0].shelves] == notches


def test_redrawing_shelf_bands_keeps_their_notch_details(page):
    bay = page.bays[0]
    edges = [200, 700, 1400, 2000, 2600]
    editing.set_shelf_edges(page, bay.index, edges)

    shelves = page.bays[0].shelves
    assert len(shelves) == 4
    assert shelves[0].y_range == (200, 700)
    assert shelves[0].notch == 33              # the band still covers the old top shelf
    assert all(shelf.inherited is False for shelf in shelves)


def test_editing_a_shelf_clears_the_borrowed_flag(page):
    bay = page.bays[1]
    assert bay.shelves_inherited is True
    shelf = editing.update_shelf(page, bay.index, 1, notch=31, depth_cm=50, slope=2)

    assert (shelf.notch, shelf.depth_cm, shelf.slope) == (31, 50, 2)
    assert shelf.inherited is False
    assert page.bays[1].shelves_inherited is False


def test_set_bay_edges_refuses_a_single_edge(page):
    with pytest.raises(ValueError, match="at least two"):
        editing.set_bay_edges(page, [100])


def test_review_summary_points_at_what_to_check(page):
    doubtful = find(page, "7008038")
    doubtful.confidence = 0.3
    nameless = find(page, "5481")
    nameless.name = ""

    summary = editing.review_summary(page)
    assert summary.total == len(page.products)
    assert summary.needs_checking >= 2
    assert summary.missing_name == 1
    assert summary.bays_sharing_shelves == [2, 3]
    assert not summary.is_clean
    assert "to check" in summary.describe()


def test_a_checked_product_stops_being_flagged(page):
    product = find(page, "7008038")
    product.confidence = 0.2
    assert editing.needs_checking(product) is True

    editing.update_product(page, product, name="Fairy 654ml Original")
    assert editing.needs_checking(product) is False


def test_duplicate_codes_are_reported(page):
    twin = find(page, "5481")
    editing.add_product(page, BBox(twin.bbox.x + 300, twin.bbox.y, 100, 80), code="5481")
    assert "5481" in editing.review_summary(page).duplicate_codes
