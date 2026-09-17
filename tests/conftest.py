"""Shared fixtures: a small hand-built layout that mirrors the real sheets."""

import os

# The UI tests need a platform plugin before Qt is imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from shelffinder.core.models import BBox, Bay, Layout, Page, Product, Shelf

# Page 2 of "IE Household 4.5m", trimmed: three bays, bays 2 and 3 share bay 1's
# shelves, and one code (209041) also appears on page 1.
PAGE_2_SHELVES = [(33, 62.0, 0.0), (22, 62.0, 0.0), (12, 62.0, 0.0), (3, 80.0, 0.0)]

PAGE_2_PRODUCTS = [
    # (code, name, cases, bay, shelf, x)
    ("250810", "The Pink Stuff Miracle Paste", 2, 1, 1, 150),
    ("217970", "Furniture Polish Beeswax Multi", 2, 1, 1, 400),
    ("202946", "Carpet& Upholstery Foam Cleaner", 2, 2, 1, 750),
    ("213350", "Platinum Dishwasher Tabs 40WL", 4, 2, 1, 1000),
    ("7175141", "All-in-1 Dishwasher Tabs 60WL", 8, 3, 1, 1300),
    ("7149115", "All-in-1 Dishwasher Tabs Lemon 60WL", 8, 3, 1, 1500),
    ("10007181", "Dishwasher Tablets Family Pack 80WL", 4, 3, 1, 1700),
    ("5481", "Finish Quantum Ultimate", 2, 3, 1, 1900),
    ("7002958", "Washing Up Liquid", 8, 1, 2, 300),
    ("7008038", "Fairy 654ml Original", 4, 1, 3, 120),
    ("1023107", "Fairy WUL Lemon", 2, 1, 3, 300),
    ("7190489", "Fairy WUL Pomegranate& Grapefruit", 2, 1, 3, 480),
    ("10076121", "Fairy Max Power 730ml", 2, 1, 3, 640),
    ("200593", "Dishwasher Salt", 4, 2, 3, 800),
    ("204356", "Dishwasher Cleaner", 8, 2, 3, 1050),
    ("209041", "All Purpose Cleaner", 2, 1, 4, 200),
]

PAGE_1_PRODUCTS = [
    ("230167", "Thick Bleach Original/Citrus", 2, 1, 1, 200),
    ("1060", "Febreze Bathroom Spring Awakening", 3, 1, 2, 150),
    ("209041", "All Purpose Cleaner", 2, 1, 2, 400),
    ("241709", "Toilet Cleaner", 4, 1, 2, 650),
]


def _make_page(number: int, total: int, entries, shelves, bay_count: int,
               name: str = "IE Household", size: str = "4.5m") -> Page:
    page = Page(number=number, total_pages=total, layout_name=name,
                layout_size=size, size=(2100, 3000))
    bay_width = 2100 / bay_count
    for index in range(1, bay_count + 1):
        bay = Bay(index=index, x_range=((index - 1) * bay_width, index * bay_width),
                  shelves_inherited=index > 1)
        for shelf_index, (notch, depth, slope) in enumerate(shelves, start=1):
            top = 200 + (shelf_index - 1) * 600
            bay.shelves.append(Shelf(index_from_top=shelf_index, y_range=(top, top + 600),
                                     notch=notch, depth_cm=depth, slope=slope,
                                     inherited=index > 1))
        page.bays.append(bay)

    for code, name, cases, bay_index, shelf_index, x in entries:
        y = 200 + (shelf_index - 1) * 600 + 250
        page.products.append(Product(code=code, name=name, cases=cases,
                                     bbox=BBox(float(x), float(y), 120.0, 90.0),
                                     bay=bay_index, shelf=shelf_index))

    # Positions, exactly as the parser assigns them.
    groups: dict[tuple[int, int], list[Product]] = {}
    for product in page.products:
        groups.setdefault((product.bay, product.shelf), []).append(product)
    for group in groups.values():
        group.sort(key=lambda p: p.bbox.cx)
        for position, product in enumerate(group, start=1):
            product.position_left = position
            product.position_right = len(group) - position + 1
    return page


@pytest.fixture
def household_layout() -> Layout:
    layout = Layout(name="IE Household", size="4.5m")
    layout.pages = [
        _make_page(1, 2, PAGE_1_PRODUCTS, PAGE_2_SHELVES[:2], bay_count=3),
        _make_page(2, 2, PAGE_2_PRODUCTS, PAGE_2_SHELVES, bay_count=3),
    ]
    return layout


@pytest.fixture
def frozen_layout() -> Layout:
    layout = Layout(name="IE Frozen", size="2.5m")
    layout.pages = [_make_page(1, 1, [("5481", "Frozen Peas", 6, 1, 1, 300),
                                      ("300380", "Ice Cream Tubs", 4, 1, 1, 700)],
                               PAGE_2_SHELVES[:1], bay_count=1,
                               name="IE Frozen", size="2.5m")]
    return layout
