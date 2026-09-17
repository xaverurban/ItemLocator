"""Headless UI tests. Run with QT_QPA_PLATFORM=offscreen (conftest sets it)."""

import os

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt                                            # noqa: E402
from PySide6.QtWidgets import QApplication                               # noqa: E402

from shelffinder.core.library import Library                             # noqa: E402
from shelffinder.core.ocr import NullOcrEngine                           # noqa: E402
from shelffinder.ui.main_window import MainWindow, NARROW_WIDTH          # noqa: E402
from shelffinder.ui.settings import AppSettings                          # noqa: E402

pytestmark = pytest.mark.ui


@pytest.fixture(scope="session")
def qt_app():
    from shelffinder.ui.app import build_application
    application = QApplication.instance() or build_application([])
    yield application


@pytest.fixture
def library(tmp_path, household_layout, frozen_layout):
    """A library holding the fixture layouts, with placeholder page images."""
    import cv2

    store = Library(str(tmp_path / "library"), ocr_engine=NullOcrEngine())
    for layout in (household_layout, frozen_layout):
        for page in layout.pages:
            width, height = page.size
            image = np.full((height, width, 3), 240, np.uint8)
            for product in page.products:
                box = product.bbox
                cv2.rectangle(image, (int(box.x), int(box.y)), (int(box.x2), int(box.y2)),
                              (40, 40, 40), 2)
            name = f"{page.id}_straight.png"
            cv2.imwrite(os.path.join(store.images_dir, name), image)
            page.straightened_image = os.path.join("images", name)
            page.transform = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        store.store.add_layout(layout)
    store.reload()
    yield store
    store.close()


@pytest.fixture
def window(qt_app, library, tmp_path):
    settings = AppSettings(data_dir=library.data_dir)
    main = MainWindow(library, settings)
    main.resize(1440, 900)
    household = next(layout for layout in library.layouts if "Household" in layout.name)
    main.open_page(household.pages[0], household)
    yield main
    main.library = library          # closeEvent closes the library; keep the fixture tidy
    main.close()


def settle(app, times: int = 3) -> None:
    for _ in range(times):
        app.processEvents()


def test_window_opens_on_a_page(window, library):
    assert window.stack.currentIndex() == 1               # the viewer, not the empty state
    assert window._current_page is not None
    assert window.viewer.page is not None
    assert "IE" in window.page_label.text()


def test_empty_library_shows_the_drop_hint(qt_app, tmp_path):
    empty = Library(str(tmp_path / "empty"), ocr_engine=NullOcrEngine())
    main = MainWindow(empty, AppSettings(data_dir=empty.data_dir))
    try:
        assert main.stack.currentIndex() == 0
        assert main.thumbnails.isHidden()
    finally:
        main.close()


def test_search_fills_the_result_card(window, qt_app):
    window.search_bar.box.setText("038")
    window.search_bar._emit()
    settle(qt_app)
    assert window.result_card.code.text() == "7008038"
    assert window.result_card.bay.value.text() == "1"
    assert window.result_card.shelf.value.text() == "3"
    assert window.result_card.position.value.text() == "1"
    assert window.result_card.cases.value.text() == "4"
    assert "page 2 of 2" in window.result_card.where.text()
    assert "1023107" in window.result_card.right_neighbour.text()


def test_single_match_jumps_without_showing_the_list(window, qt_app):
    index = window.search_bar.scope.findData(
        next(layout.id for layout in window.library.layouts if "Household" in layout.name))
    window.search_bar.scope.setCurrentIndex(index)        # the household layout only
    window.search_bar.box.setText("038")
    window.search_bar._emit()
    settle(qt_app)
    assert not window.results.isVisible()
    assert window._current_page.number == 2


def test_several_matches_open_the_list(window, qt_app):
    window.search_bar.box.setText("5481")                 # in both layouts
    window.search_bar._emit()
    settle(qt_app)
    assert window.results.count() == 2
    assert window.result_card.code.text() == "5481"


def test_no_match_offers_near_misses(window, qt_app):
    window.search_bar.box.setText("7008039")
    window.search_bar._emit()
    settle(qt_app)
    assert window.results.count() >= 1
    assert "Did you mean" in window.statusBar().currentMessage()


def test_short_query_does_not_search(window, qt_app):
    window.search_bar.box.setText("03")
    window.search_bar._emit()
    settle(qt_app)
    assert not window.results.isVisible()
    assert "at least 3 digits" in window.statusBar().currentMessage()


def test_escape_clears_the_search(window, qt_app):
    window.search_bar.box.setText("038")
    window.search_bar._emit()
    settle(qt_app)
    window._clear_search()
    assert window.search_bar.text() == ""
    assert window.result_card.code.text() == "-"
    assert window.viewer._product is None


def test_highlight_dims_the_rest_of_the_page(window, qt_app):
    window.search_bar.box.setText("038")
    window.search_bar._emit()
    settle(qt_app)
    dim = window.viewer._dim_item
    assert dim is not None
    assert not dim.path().isEmpty()
    assert dim.brush().color().alpha() > 0
    assert window.viewer._highlight_item.isVisible()
    assert window.viewer._shelf_item.isVisible()
    assert window.viewer._bay_item.isVisible()


def test_dim_level_setting_reaches_the_viewer(window, qt_app):
    window.apply_settings(window.settings.with_changes(dim_level=0))
    window.search_bar.box.setText("038")
    window.search_bar._emit()
    settle(qt_app)
    assert window.viewer._dim_item.brush().color().alpha() == 0


def test_clicking_a_product_shows_its_card(window, qt_app):
    page = window._current_page
    product = page.products[1]
    window._clicked_on_page((product.bbox.cx, product.bbox.cy))
    settle(qt_app)
    assert window.result_card.code.text() == product.code


def test_clicking_empty_space_changes_nothing(window, qt_app):
    window.search_bar.box.setText("038")
    window.search_bar._emit()
    settle(qt_app)
    window._clicked_on_page((2.0, 2.0))
    assert window.result_card.code.text() == "7008038"


def test_page_navigation(window, qt_app):
    assert len(window._current_layout.pages) > 1
    start = window._current_page.number
    window.step_page(1)
    assert window._current_page.number != start
    window.step_page(-1)
    assert window._current_page.number == start
    window.step_page(-5)                                   # clamped at the first page
    assert window._current_page.number == min(
        page.number for page in window._current_layout.pages)


def test_thumbnails_follow_the_layout(window):
    assert window.thumbnails.count() == len(window._current_layout.pages)


def test_panels_stack_on_a_narrow_window(window):
    window.apply_responsive_layout(NARROW_WIDTH - 200)
    assert window.splitter.orientation() == Qt.Orientation.Vertical
    window.apply_responsive_layout(NARROW_WIDTH + 200)
    assert window.splitter.orientation() == Qt.Orientation.Horizontal


def test_sidebar_hides_itself_when_very_narrow(window):
    window.apply_responsive_layout(700)
    assert window.sidebar_holder.isHidden()
    window.apply_responsive_layout(1400)
    assert not window.sidebar_holder.isHidden()


def test_toggle_to_the_original_keeps_the_highlight(window, qt_app):
    window.search_bar.box.setText("038")
    window.search_bar._emit()
    settle(qt_app)
    straight = window.viewer._highlight_item.polygon().boundingRect()

    window.original_toggle.setChecked(True)
    window._toggle_original()
    settle(qt_app)
    # The placeholder transform is the identity, so the box lands in the same
    # place; what matters is that it is still drawn.
    assert window.viewer.showing_original
    assert window.viewer._highlight_item.isVisible()
    assert window.viewer._highlight_item.polygon().boundingRect() == straight


def test_settings_dialog_round_trip(qt_app, library):
    from shelffinder.ui.settings_dialog import SettingsDialog
    settings = AppSettings(data_dir=library.data_dir)
    dialog = SettingsDialog(settings, library.layouts)
    dialog.dim.setValue(30)
    dialog.scope.setCurrentIndex(1)
    updated = dialog.result_settings()
    assert updated.dim_level == 30
    assert updated.default_scope == library.layouts[0].id
    assert updated.data_dir == settings.data_dir


def test_drop_of_unsupported_files_is_reported(window):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QDropEvent
    from PySide6.QtCore import QPointF

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("/tmp/not-a-sheet.txt")])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(event)
    assert "not layout sheets" in window.statusBar().currentMessage()
