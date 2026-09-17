"""Text rules, including the mangled strings OCR actually produces."""

import pytest

from shelffinder.core import textparse as tp


@pytest.mark.parametrize("text,expected", [
    ("Notch: 33 Depth:62cm Slope:0", (33, 62.0, 0.0)),
    ("Notch:33Depth:62cmSlope:0", (33, 62.0, 0.0)),        # OCR drops the spaces
    ("Notch: 3 Depth:80cm Slope:0", (3, 80.0, 0.0)),
    ("N0tch: 22 Depth 62cm Slope 0", (22, 62.0, 0.0)),     # o read as zero
    ("Notch: 12 Depth:62cm Slope:-2", (12, 62.0, -2.0)),
    ("Notch:19Depth:62.5cmSlope:0", (19, 62.5, 0.0)),
])
def test_parse_notch(text, expected):
    info = tp.parse_notch(text)
    assert info is not None
    assert (info.notch, info.depth_cm, info.slope) == expected


@pytest.mark.parametrize("text", [
    "Ambient Layouts: First visible notch above the plinth is notch 4.",
    "Chiller Layouts: First visible notch above the base is notch 1",
    "Fairy 654ml Original",
    "",
])
def test_parse_notch_rejects_prose(text):
    assert tp.parse_notch(text) is None


@pytest.mark.parametrize("text,expected", [
    ("Cases:4", 4), ("Cases 8", 8), ("Cases.2", 2), ("cases:12", 12), ("Ca5es:6", 6),
])
def test_parse_cases(text, expected):
    assert tp.parse_cases(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("7008038", "7008038"), ("5481", "5481"), ("1060", "1060"), ("65810", "65810"),
    ("10076121", "10076121"),
    ("l0176277", "10176277"),      # letter l read for 1
    ("B481", "8481"),              # B read for 8
    ("7OO8O38", "7008038"),        # O read for 0
])
def test_code_candidate_normalises(text, expected):
    assert tp.code_candidate(text) == expected


@pytest.mark.parametrize("text", [
    "Fairy 654ml Original", "Cases:4", "Notch: 33 Depth:62cm Slope:0",
    "2 of 2", "12", "Glass", "Dishwasher Salt",
])
def test_code_candidate_rejects_non_codes(text):
    assert tp.code_candidate(text) is None


def test_parse_header():
    assert tp.parse_header("IE Household 4.5m") == ("IE Household", "4.5m")
    assert tp.parse_header("IE Household 4,5 m") == ("IE Household", "4.5m")
    assert tp.parse_header("IE Frozen 2.5m") == ("IE Frozen", "2.5m")


def test_parse_page_number():
    assert tp.parse_page_number("1 of 2") == (1, 2)
    assert tp.parse_page_number("2 of 2") == (2, 2)
    assert tp.parse_page_number("3 of 2") is None       # page beyond the total
    assert tp.parse_page_number("Cases:4") is None


def test_markers_and_noise():
    assert tp.is_marker("NTA")
    assert not tp.is_marker("Fairy")
    assert tp.is_noise("Customer Flow")
    assert tp.is_noise("Contact layoutmanagement@lidl.ie with any queries/suggestions")
    assert not tp.is_noise("Fairy 654ml Original")


def test_clean_name_joins_wrapped_lines():
    assert tp.clean_name(["Fairy WUL", "Pomegranate&", "Grapefruit"]) == \
        "Fairy WUL Pomegranate& Grapefruit"
    assert tp.clean_name(["  Toilet ", "", "Blocks WK9 "]) == "Toilet Blocks WK9"


def test_near_miss_codes():
    misses = tp.near_miss_codes("038")
    assert "138" in misses and "030" in misses and "038" not in misses
    assert len(misses) == 27


@pytest.mark.parametrize("text,expected", [
    ("Notch:33Denth:62cmSlope:Q", (33, 62.0, 0.0)),    # p read as n, 0 read as Q
    ("Notch: 3 Depth:8Ocm Slope:O", (3, 80.0, 0.0)),   # 0 read as O next to a digit
])
def test_parse_notch_folds_digit_lookalikes(text, expected):
    info = tp.parse_notch(text)
    assert info is not None
    assert (info.notch, info.depth_cm, info.slope) == expected


def test_fold_number_letters_leaves_words_alone():
    assert tp.fold_number_letters("Depth") == "Depth"
    assert tp.fold_number_letters("Slope:Q") == "Slope:0"
    assert tp.fold_number_letters("8Ocm") == "80cm"
    assert tp.fold_number_letters("Fairy Original") == "Fairy Original"
