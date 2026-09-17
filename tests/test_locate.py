"""The result card: bay, shelf, position, notch and neighbours."""

import pytest

from shelffinder.core.locate import locate, locate_hit, neighbours, shelf_row_products
from shelffinder.core.search import ProductIndex


@pytest.fixture
def index(household_layout) -> ProductIndex:
    return ProductIndex([household_layout])


def find(layout, code, page_number=2):
    page = next(p for p in layout.pages if p.number == page_number)
    return next(product for product in page.products if product.code == code), page


def test_fairy_result_card(household_layout, index):
    """Acceptance test: "038" is the leftmost product on the notch 12 shelf."""
    product, page = find(household_layout, "7008038")
    card = locate(product, page, household_layout)

    assert card.page_label() == "IE Household 4.5m, page 2 of 2"
    assert card.bay_label() == "Bay 1 of 3"
    assert card.shelf_label() == "Shelf 3 from top, 2 from bottom"
    assert card.notch_label() == "Notch 12, depth 62cm, slope 0"
    assert card.position_label() == "Position 1 from left, 4 from right of 4"
    assert card.cases == 4


def test_finish_quantum_is_rightmost_on_the_top_shelf(household_layout):
    """Acceptance test: "5481" is the rightmost product on the top shelf."""
    product, page = find(household_layout, "5481")
    card = locate(product, page, household_layout)
    assert card.bay_index == 3 and card.bay_count == 3
    assert card.shelf_from_top == 1
    assert card.position_right == 1
    assert card.notch_label().startswith("Notch 33")


def test_neighbours_within_a_bay(household_layout):
    product, page = find(household_layout, "1023107")
    card = locate(product, page, household_layout)
    assert card.neighbour_left.code == "7008038"
    assert card.neighbour_right.code == "7190489"
    assert card.neighbour_left.same_bay is True


def test_neighbours_cross_the_bay_line(household_layout):
    """The product to the right can sit in the next bay - say so."""
    product, page = find(household_layout, "10076121")     # last product of bay 1
    card = locate(product, page, household_layout)
    assert card.neighbour_left.code == "7190489"
    assert card.neighbour_right.code == "200593"           # first product of bay 2
    assert card.neighbour_right.same_bay is False
    assert card.neighbour_right.describe().endswith("(next bay)")


def test_first_product_on_a_row_has_no_left_neighbour(household_layout):
    product, page = find(household_layout, "250810")
    card = locate(product, page, household_layout)
    assert card.neighbour_left is None
    assert card.neighbour_right.code == "217970"


def test_shelf_row_crosses_every_bay(household_layout):
    product, page = find(household_layout, "213350")
    row = [item.code for item in shelf_row_products(page, product)]
    assert row == ["250810", "217970", "202946", "213350",
                   "7175141", "7149115", "10007181", "5481"]


def test_reversed_customer_flow_flips_bays_and_neighbours(household_layout):
    product, page = find(household_layout, "10076121")
    page.customer_flow_reversed = True
    card = locate(product, page, household_layout)
    assert card.bay_index == 3            # bay 1 on the page, third in flow order
    assert card.neighbour_left.code == "200593"
    assert card.neighbour_right.code == "7190489"


def test_shared_shelves_mark_the_card_for_review(household_layout):
    product, page = find(household_layout, "213350")       # bay 2, shelves inherited
    card = locate(product, page, household_layout)
    assert card.needs_review is True
    product, page = find(household_layout, "7008038")      # bay 1, its own shelves
    assert locate(product, page, household_layout).needs_review is False


def test_summary_lines_read_like_the_card(household_layout):
    product, page = find(household_layout, "7008038")
    lines = locate(product, page, household_layout).summary_lines()
    assert lines[0] == "7008038  Fairy 654ml Original"
    assert lines[1] == "IE Household 4.5m, page 2 of 2"
    assert "Cases: 4" in lines
    assert any(line.startswith("Neighbours") for line in lines)


def test_locate_hit_matches_locate(household_layout, index):
    hit = index.search("038").hits[0]
    card = locate_hit(hit)
    assert card.code == "7008038"
    assert card.page_label() == "IE Household 4.5m, page 2 of 2"


def test_missing_shelf_data_degrades_gracefully(household_layout):
    product, page = find(household_layout, "7008038")
    page.bays[0].shelves = []
    card = locate(product, page, household_layout)
    assert card.notch_label() == "Notch unknown"
    assert card.shelf_from_bottom == 0
    assert card.needs_review is False or card.shelf is None


def test_the_shelf_above_is_not_a_neighbour(household_layout):
    """Rows are matched by shelf height band, not by proximity in pixels."""
    product, page = find(household_layout, "7002958")      # alone on shelf 2
    row = [item.code for item in shelf_row_products(page, product)]
    assert row == ["7002958"]
    card = locate(product, page, household_layout)
    assert card.neighbour_left is None and card.neighbour_right is None


def test_bays_with_different_shelf_counts_still_pair_up(household_layout):
    """Page 1 has fewer shelves than page 2 - rows must not leak across bands."""
    product, page = find(household_layout, "1060", page_number=1)
    row = [item.code for item in shelf_row_products(page, product)]
    assert "230167" not in row            # that one is on the shelf above
    assert set(row) == {"1060", "209041", "241709"}
