"""The review screen, driven headlessly."""

import os

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF                                       # noqa: E402
from PySide6.QtWidgets import QApplication                               # noqa: E402

from shelffinder.core import editing                                     # noqa: E402
from shelffinder.core.library import Library                             # noqa: E402
from shelffinder.core.models import BBox                                 # noqa: E402
from shelffinder.core.ocr import NullOcrEngine                           # noqa: E402
from shelffinder.ui.review import ReviewDialog                           # noqa: E402

pytestmark = pytest.mark.ui


@pytest.fixture(scope="session")
def qt_app():
    from shelffinder.ui.app import build_application
    yield QApplication.instance() or build_application([])


@pytest.fixture
def library(tmp_path, household_layout):
    import cv2

    store = Library(str(tmp_path / "library"), ocr_engine=NullOcrEngine())
    for page in household_layout.pages:
        width, height = page.size
        image = np.full((height, width, 3), 240, np.uint8)
        name = f"{page.id}_straight.png"
        cv2.imwrite(os.path.join(store.images_dir, name), image)
        page.straightened_image = os.path.join("images", name)
    store.store.add_layout(household_layout)
    store.reload()
    yield store
    store.close()


@pytest.fixture
def dialog(qt_app, library):
    layout = library.layouts[0]
    page = next(page for page in layout.pages if page.number == 2)
    review = ReviewDialog(page, library.page_image_path(page))
    yield review
    review.close()


def product_named(dialog, code):
    return next(p for p in dialog.page.products if p.code == code)


def test_the_page_opens_with_every_product_listed(dialog):
    assert dialog.table.rowCount() == len(dialog.page.products)
    assert dialog.canvas._boxes, "every product should have a box on the page"
    assert [guide for guide in dialog.canvas._guides if guide.vertical], "bay dividers"
    assert [guide for guide in dialog.canvas._guides if not guide.vertical], "shelf rules"
    assert "PRODUCTS" in dialog.summary.text().upper()


def test_editing_works_on_a_copy_until_it_is_saved(dialog, library):
    original = next(page for page in library.layouts[0].pages if page.number == 2)
    assert dialog.page is not original
    assert dialog.page.id == original.id

    product = product_named(dialog, "7008038")
    dialog.canvas.select_product(product)
    dialog.code_field.setText("7008999")
    dialog._apply_product_edits()

    assert product_named(dialog, "7008999").manually_edited is True
    # The stored page still says what it said.
    assert any(p.code == "7008038" for p in original.products)


def test_saving_writes_the_corrections_back(dialog, library, qt_app):
    saved = []
    dialog.pageSaved.connect(saved.append)

    product = product_named(dialog, "7008038")
    dialog.canvas.select_product(product)
    dialog.name_field.setText("Fairy Original 654ml")
    dialog._apply_product_edits()
    dialog.accept()

    assert len(saved) == 1
    library.save_page(saved[0])
    reloaded = next(page for page in library.layouts[0].pages if page.number == 2)
    fairy = next(p for p in reloaded.products if p.code == "7008038")
    assert fairy.name == "Fairy Original 654ml"
    assert fairy.manually_edited is True


def test_a_correction_clears_the_needs_checking_flag(dialog):
    product = product_named(dialog, "5481")
    product.confidence = 0.3
    assert editing.needs_checking(product) is True

    dialog.canvas.select_product(product)
    dialog.code_field.setText("5481")
    dialog._apply_product_edits()
    assert editing.needs_checking(product_named(dialog, "5481")) is False


def test_the_filter_shows_only_what_needs_checking(dialog):
    product_named(dialog, "7008038").confidence = 0.2
    dialog.only_flagged.setChecked(True)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "7008038"

    dialog.only_flagged.setChecked(False)
    assert dialog.table.rowCount() == len(dialog.page.products)


def test_adding_a_product_by_drawing_a_box(dialog):
    before = len(dialog.page.products)
    bay = dialog.page.bays[0]
    shelf = bay.shelves[0]
    dialog._draw_finished(BBox(bay.x_range[0] + 20, shelf.y_range[0] + 20, 120, 90))

    assert len(dialog.page.products) == before + 1
    added = dialog.page.products[-1]
    assert added.bay == 1 and added.shelf == 1
    assert "added-by-hand" in added.tags
    assert dialog.table.rowCount() == before + 1


def test_deleting_a_product_renumbers_its_shelf(dialog):
    lemon = product_named(dialog, "1023107")               # position 2 of 4
    dialog.canvas.select_product(lemon)
    dialog.delete_selected()

    assert all(p.code != "1023107" for p in dialog.page.products)
    assert product_named(dialog, "7190489").position_left == 2


def test_dragging_a_box_moves_the_product_to_another_shelf(dialog):
    product = product_named(dialog, "7008038")             # bay 1, shelf 3
    top_shelf = dialog.page.bays[0].shelves[0]
    dialog._box_moved(product, BBox(200, top_shelf.y_range[0] + 30, 120, 90))

    assert product_named(dialog, "7008038").shelf == 1


def test_dragging_a_bay_line_re_splits_the_page(dialog):
    guides = [guide for guide in dialog.canvas._guides if guide.vertical]
    assert guides, "there should be bay dividers to drag"

    first = guides[0]
    first.moveBy(200, 0)
    dialog._guide_moved(first)

    edges = [bay.x_range for bay in dialog.page.bays]
    assert len(edges) == 3
    assert edges[0][1] == pytest.approx(900, abs=1)


def test_editing_a_shelf_makes_it_the_bays_own(dialog):
    product = next(p for p in dialog.page.products if p.bay == 2)
    dialog.canvas.select_product(product)
    dialog.notch_field.setValue(29)
    dialog._apply_shelf_edits()

    bay = next(bay for bay in dialog.page.bays if bay.index == 2)
    assert bay.shelves_inherited is False
    assert bay.shelves[product.shelf - 1].notch == 29


def test_saving_records_what_is_still_unchecked(dialog):
    product_named(dialog, "7008038").confidence = 0.2
    saved = []
    dialog.pageSaved.connect(saved.append)
    dialog.accept()

    assert any("still need checking" in warning for warning in saved[0].warnings)
