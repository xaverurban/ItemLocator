"""Search behaviour: match priority, live typing, near misses, scope."""

import pytest

from shelffinder.core.search import MatchKind, ProductIndex, MIN_QUERY_DIGITS


@pytest.fixture
def index(household_layout, frozen_layout) -> ProductIndex:
    return ProductIndex([household_layout, frozen_layout])


def codes(result) -> list[str]:
    return [hit.product.code for hit in result.hits]


def test_short_queries_do_not_search(index):
    for query in ("", "0", "03"):
        result = index.search(query)
        assert result.too_short and result.hits == []
    assert not index.search("038").too_short
    assert MIN_QUERY_DIGITS == 3


def test_suffix_match_wins(index, household_layout):
    """Acceptance test: "038" finds 7008038, above a code that merely contains it."""
    result = index.search("038")
    top = result.hits[0]
    assert top.product.code == "7008038"
    assert top.kind is MatchKind.SUFFIX
    assert top.highlight() == ("7008", "038", "")
    assert [hit.kind for hit in result.hits] == [MatchKind.SUFFIX, MatchKind.CONTAINS]

    # Inside one layout it is the only match, so the UI jumps straight to it.
    scoped = index.search("038", layout_ids=[household_layout.id])
    assert scoped.single is not None
    assert scoped.single.product.code == "7008038"


def test_exact_match_sorts_above_suffix_and_contains(index):
    result = index.search("5481")
    assert result.hits[0].kind is MatchKind.EXACT
    # The same code in two layouts: both locations are listed.
    assert codes(result) == ["5481", "5481"]
    assert {hit.layout.name for hit in result.hits} == {"IE Household", "IE Frozen"}


def test_priority_is_exact_then_suffix_then_contains(index):
    result = index.search("041")
    kinds = [hit.kind for hit in result.hits]
    assert kinds == sorted(kinds, reverse=True)
    assert all(kind is MatchKind.SUFFIX for kind in kinds)

    mixed = index.search("038")
    by_code = {hit.product.code: hit.kind for hit in mixed.hits}
    assert by_code["7008038"] is MatchKind.SUFFIX
    assert by_code["300380"] is MatchKind.CONTAINS
    assert [hit.kind for hit in mixed.hits] == sorted(
        (hit.kind for hit in mixed.hits), reverse=True)


def test_typing_narrows_live(index):
    assert len(index.search("100").hits) >= 1
    assert codes(index.search("10007")) == ["10007181"]
    assert codes(index.search("1000718")) == ["10007181"]


def test_a_code_on_several_shelves_returns_every_location(index):
    result = index.search("209041")
    assert len(result.hits) == 2
    assert {(hit.page.number, hit.product.shelf) for hit in result.hits} == {(1, 2), (2, 4)}


def test_no_match_reports_what_was_searched(index):
    result = index.search("999")
    assert result.is_empty
    assert result.message().startswith("No product ending in 999")


def test_near_misses_catch_a_wrong_digit(index):
    """An OCR slip in the code should still lead somewhere."""
    result = index.search("038038")           # nothing ends in this
    assert result.is_empty
    result = index.search("7008039")          # last digit misread
    assert result.is_empty
    assert [hit.product.code for hit in result.suggestions] == ["7008038"]
    assert result.suggestions[0].reason == "one digit different"
    assert "Did you mean 7008038" in result.message()


def test_near_misses_catch_swapped_digits(index):
    result = index.search("7149151")          # last two digits swapped
    assert result.is_empty
    assert "7149115" in [hit.product.code for hit in result.suggestions]


def test_scope_limits_the_search_to_one_layout(index, household_layout, frozen_layout):
    everywhere = index.search("5481")
    assert len(everywhere.hits) == 2
    household_only = index.search("5481", layout_ids=[household_layout.id])
    assert len(household_only.hits) == 1
    assert household_only.single.layout.id == household_layout.id


def test_results_are_ordered_for_a_stable_list(index):
    result = index.search("1", layout_ids=None)  # too short
    assert result.too_short
    result = index.search("115")
    ordering = [(hit.layout.title, hit.page.number, hit.product.bay, hit.product.shelf,
                 hit.product.position_left) for hit in result.hits]
    assert ordering == sorted(ordering)


def test_letters_in_the_query_are_ignored(index):
    assert index.search("o38").hits[0].product.code == "7008038"    # typed O for zero
    assert codes(index.search(" 038 ")) == codes(index.search("038"))


def test_limit_marks_the_result_truncated(index):
    result = index.search("0", limit=2)
    assert result.too_short
    result = index.search("100", limit=1)
    assert len(result.hits) == 1
    if result.truncated:
        assert len(index.search("100").hits) > 1


def test_index_maintenance(household_layout, frozen_layout):
    index = ProductIndex([household_layout])
    first = len(index)
    index.add_layout(frozen_layout)
    assert len(index) > first
    index.remove_layout(frozen_layout.id)
    assert len(index) == first
    index.rebuild([frozen_layout])
    assert [layout.id for layout in index.layouts] == [frozen_layout.id]


def test_reverse_lookup_from_a_click(index, household_layout):
    page = household_layout.pages[1]
    product = next(p for p in page.products if p.code == "7008038")
    box = product.bbox
    assert index.product_at(page, box.cx, box.cy) is product
    assert index.product_at(page, 5, 5) is None
