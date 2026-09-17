"""Data model round-tripping and page grouping."""

from shelffinder.core.models import BBox, Bay, Layout, Page, Product, Shelf, \
    group_pages_into_layouts


def make_page(number: int, name: str = "IE Household", size: str = "4.5m") -> Page:
    page = Page(number=number, total_pages=2, layout_name=name, layout_size=size)
    shelf = Shelf(index_from_top=1, y_range=(10.0, 100.0), notch=33, depth_cm=62.0, slope=0.0)
    page.bays = [Bay(index=1, x_range=(0.0, 50.0), shelves=[shelf])]
    page.products = [Product(code="7008038", name="Fairy 654ml Original", cases=4,
                             bbox=BBox(1, 2, 3, 4), bay=1, shelf=1,
                             position_left=1, position_right=3)]
    return page


def test_page_round_trip():
    page = make_page(1)
    restored = Page.from_dict(page.to_dict())
    assert restored.number == 1
    assert restored.products[0].code == "7008038"
    assert restored.products[0].bbox.as_tuple() == (1, 2, 3, 4)
    assert restored.bays[0].shelves[0].notch == 33
    assert restored.bays[0].shelves[0].y_range == (10.0, 100.0)


def test_layout_round_trip():
    layout = Layout(name="IE Household", size="4.5m", pages=[make_page(1), make_page(2)])
    restored = Layout.from_dict(layout.to_dict())
    assert restored.title == "IE Household 4.5m"
    assert [p.number for p in restored.pages] == [1, 2]
    assert len(list(restored.iter_products())) == 2


def test_grouping_ignores_ocr_spacing():
    pages = [make_page(2, "IEHousehold"), make_page(1, "IE Household"),
             make_page(1, "IE Frozen", "2.5m")]
    layouts = group_pages_into_layouts(pages)
    assert len(layouts) == 2
    household = next(lay for lay in layouts if "Household" in lay.name)
    assert [p.number for p in household.pages] == [1, 2]
    assert household.name == "IE Household"      # the readable spelling wins


def test_bbox_helpers():
    box = BBox(10, 20, 30, 40)
    assert (box.x2, box.y2, box.cx, box.cy) == (40, 60, 25, 40)
    joined = box.union(BBox(0, 0, 5, 5))
    assert joined.as_tuple() == (0, 0, 40, 60)
    assert BBox.from_xyxy(40, 60, 10, 20).as_tuple() == (10, 20, 30, 40)
