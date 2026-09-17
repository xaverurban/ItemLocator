"""The main window: sidebar, search, viewer and result card."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
                               QLabel, QMainWindow, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from ..core import editing
from ..core.imaging import SUPPORTED_EXTENSIONS
from ..core.library import ImportReport, Library
from ..core.locate import locate
from ..core.models import Layout, Page, Product
from ..core.store import ImportMode
from . import theme
from .import_task import ImportWorker, describe, describe_report
from .result_card import ResultCard
from .review import ReviewDialog
from .search_bar import ResultList, SearchBar
from .settings import AppSettings
from .settings_dialog import SettingsDialog
from .sidebar import LayoutSidebar, ThumbnailStrip
from .viewer import PageViewer

NARROW_WIDTH = 1040          # below this the panels stack instead of sitting side by side


class MainWindow(QMainWindow):
    libraryChanged = Signal()

    def __init__(self, library: Library, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.library = library
        self.settings = settings
        self.setWindowTitle("ShelfFinder")
        self.resize(1440, 920)
        self.setAcceptDrops(True)

        self._current_page: Optional[Page] = None
        self._current_layout: Optional[Layout] = None
        self._worker: Optional[ImportWorker] = None

        self._build_ui()
        self._build_shortcuts()
        self.apply_settings(settings)
        self.refresh_library(select_first=True)

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 14, 14, 10)
        outer.setSpacing(10)

        # -- top bar
        top = QHBoxLayout()
        top.setSpacing(8)
        self.sidebar_button = QPushButton("☰")
        self.sidebar_button.setFixedWidth(40)
        self.sidebar_button.setCheckable(True)
        self.sidebar_button.setChecked(True)
        self.sidebar_button.setToolTip("Show or hide the layouts panel")
        self.sidebar_button.clicked.connect(self._toggle_sidebar)
        top.addWidget(self.sidebar_button)

        self.search_bar = SearchBar(self)
        self.search_bar.queryChanged.connect(self._run_search)
        self.search_bar.submitted.connect(self._open_top_result)
        self.search_bar.escaped.connect(self._clear_search)
        self.search_bar.navigate.connect(self._move_selection)
        top.addWidget(self.search_bar, 1)

        self.import_button = QPushButton("Import sheets")
        self.import_button.setObjectName("Primary")
        self.import_button.clicked.connect(self.choose_files)
        top.addWidget(self.import_button)

        self.packs_button = QPushButton("Packs")
        self.packs_button.setToolTip("Move a processed layout to another machine "
                                     "or to the phone app")
        packs_menu = QMenu(self)
        packs_menu.addAction("Export a layout pack...", self.export_pack)
        packs_menu.addAction("Import a layout pack...", self.import_pack)
        self.packs_button.setMenu(packs_menu)
        top.addWidget(self.packs_button)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.open_settings)
        top.addWidget(self.settings_button)
        outer.addLayout(top)

        # -- middle
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(10)

        self.sidebar = LayoutSidebar(self)
        self.sidebar.pageSelected.connect(self._page_selected)
        sidebar_holder = QFrame()
        sidebar_holder.setObjectName("Panel")
        sidebar_layout = QVBoxLayout(sidebar_holder)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.addWidget(self.sidebar)
        sidebar_holder.setMinimumWidth(240)
        self.sidebar_holder = sidebar_holder
        self.splitter.addWidget(sidebar_holder)

        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(0, 0, 0, 0)
        centre_layout.setSpacing(8)

        self.stack = QStackedWidget()
        self.viewer = PageViewer(self)
        self.viewer.productClicked.connect(self._clicked_on_page)

        empty = QFrame()
        empty.setObjectName("Panel")
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label = QLabel("Drop layout sheets here")
        empty_label.setObjectName("EmptyState")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("JPG, PNG, HEIC or PDF  ·  Ctrl+O to browse")
        hint.setObjectName("Hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_label)
        empty_layout.addWidget(hint)
        self.stack.addWidget(empty)
        self.stack.addWidget(self.viewer)
        centre_layout.addWidget(self.stack, 1)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.page_label = QLabel("")
        self.page_label.setObjectName("Hint")
        controls.addWidget(self.page_label, 1)
        self.review_button = QPushButton("Review page")
        self.review_button.setToolTip("Check what was read on this page and fix it (Ctrl+R)")
        self.review_button.clicked.connect(self.review_current_page)
        controls.addWidget(self.review_button)

        self.original_toggle = QPushButton("Original photo")
        self.original_toggle.setCheckable(True)
        self.original_toggle.setToolTip("Switch between the straightened page and the photo")
        self.original_toggle.clicked.connect(self._toggle_original)
        controls.addWidget(self.original_toggle)
        fit_button = QPushButton("Fit page")
        fit_button.clicked.connect(self.viewer.fit_page)
        controls.addWidget(fit_button)
        centre_layout.addLayout(controls)

        self.thumbnails = ThumbnailStrip(self)
        self.thumbnails.setVisible(False)
        self.thumbnails.pageChosen.connect(lambda page: self.open_page(page))
        centre_layout.addWidget(self.thumbnails)
        self.splitter.addWidget(centre)

        self.result_card = ResultCard(self)
        self.splitter.addWidget(self.result_card)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([250, 900, 340])
        outer.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        # -- results popup
        self.results = ResultList(self)
        self.results.setWindowFlags(Qt.WindowType.Popup)
        self.results.hitChosen.connect(self._open_hit)
        self.results.hitHighlighted.connect(lambda hit: self._show_hit(hit, animate=True))
        self.results.hide()

        # -- status bar
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage("Ready")

    def _build_shortcuts(self) -> None:
        def shortcut(keys: str, slot) -> None:
            action = QShortcut(QKeySequence(keys), self)
            action.activated.connect(slot)

        shortcut("Ctrl+O", self.choose_files)
        shortcut("Ctrl+F", self.search_bar.focus)
        shortcut("/", self.search_bar.focus)
        shortcut("Ctrl+,", self.open_settings)
        shortcut("Left", lambda: self.step_page(-1))
        shortcut("Right", lambda: self.step_page(1))
        shortcut("Ctrl+B", self.sidebar_button.click)
        shortcut("Ctrl+R", self.review_current_page)
        shortcut("Escape", self._clear_search)

    # ------------------------------------------------------- settings
    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        palette = theme.Palette(accent=settings.accent_colour,
                                highlight=settings.highlight_colour)
        application = QApplication.instance()
        if application is not None:
            application.setStyleSheet(theme.stylesheet(palette))
        self.viewer.set_highlight_colour(settings.highlight_colour)
        self.viewer.set_dim_level(settings.dim_level)
        self.sidebar_button.setChecked(settings.sidebar_visible)
        self.sidebar_holder.setVisible(settings.sidebar_visible)
        self.original_toggle.setChecked(settings.show_original)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.library.layouts, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        updated = dialog.result_settings()
        moved = updated.data_dir != self.settings.data_dir
        if moved:
            try:
                self.library.copy_data_folder(updated.data_dir)
            except OSError as error:
                QMessageBox.warning(self, "Could not move the data folder", str(error))
                updated = updated.with_changes(data_dir=self.settings.data_dir)
        updated.save()
        self.apply_settings(updated)
        if moved:
            self.refresh_library(select_first=True)
        self.statusBar().showMessage("Settings saved", 4000)

    # ------------------------------------------------------- library
    def refresh_library(self, select_first: bool = False) -> None:
        layouts = self.library.layouts
        self.sidebar.set_layouts(layouts, self._current_page.id if self._current_page else "")
        self.search_bar.set_layouts(layouts, self.settings.default_scope)
        stats = self.library.stats()
        self.statusBar().showMessage(
            f"{stats['layouts']} layout(s), {stats['pages']} page(s), "
            f"{stats['products']} products")
        if select_first and layouts and layouts[0].pages:
            self.open_page(layouts[0].pages[0], layouts[0])
        elif not layouts:
            self.stack.setCurrentIndex(0)
        self.libraryChanged.emit()

    def open_page(self, page: Page, layout: Optional[Layout] = None,
                  keep_view: bool = False) -> None:
        layout = layout or self.library.layout_of(page)
        self._current_page = page
        self._current_layout = layout
        path = self.library.page_image_path(page, original=self.original_toggle.isChecked())
        if not self.viewer.show_page(page, path, original=self.original_toggle.isChecked(),
                                     keep_view=keep_view):
            self.stack.setCurrentIndex(0)
            self.statusBar().showMessage(f"The image for page {page.number} is missing", 6000)
            return
        self.stack.setCurrentIndex(1)
        title = layout.title if layout else ""
        total = f" of {page.total_pages}" if page.total_pages else ""
        summary = editing.review_summary(page)
        note = f"   ·   {summary.needs_checking} to check" if summary.needs_checking else ""
        self.page_label.setText(f"{title}   ·   page {page.number}{total}   ·   "
                                f"{len(page.products)} products{note}")
        self.page_label.setToolTip("\n".join(page.warnings))
        self.page_label.setStyleSheet(
            f"color: {theme.AMBER};" if summary.needs_checking else "")
        self.review_button.setText(
            f"Review page ({summary.needs_checking})" if summary.needs_checking
            else "Review page")
        self.thumbnails.set_pages(layout, lambda p: self.library.page_image_path(p), page.id)
        self.sidebar.select_page(page)

    def step_page(self, delta: int) -> None:
        if self._current_layout is None or self._current_page is None:
            return
        pages = self._current_layout.pages
        index = next((i for i, page in enumerate(pages)
                      if page.id == self._current_page.id), None)
        if index is None:
            return
        new_index = max(0, min(len(pages) - 1, index + delta))
        if new_index != index:
            self.open_page(pages[new_index], self._current_layout)

    def _page_selected(self, page: Page, layout: Layout) -> None:
        self.open_page(page, layout)

    def _toggle_sidebar(self) -> None:
        visible = self.sidebar_button.isChecked()
        self.sidebar_holder.setVisible(visible)
        self.settings = self.settings.with_changes(sidebar_visible=visible)
        self.settings.save()

    def _toggle_original(self) -> None:
        if self._current_page is None:
            self.original_toggle.setChecked(False)
            return
        original = self.original_toggle.isChecked()
        path = self.library.page_image_path(self._current_page, original=original)
        if not path:
            self.original_toggle.setChecked(not original)
            self.statusBar().showMessage("That image is not stored for this page", 5000)
            return
        self.viewer.show_page(self._current_page, path, original=original)
        self.settings = self.settings.with_changes(show_original=original)
        self.settings.save()

    # ------------------------------------------------------- searching
    def _run_search(self, text: str, layout_ids) -> None:
        result = self.library.search(text, layout_ids=layout_ids)
        if result.too_short:
            self.results.hide()
            if text.strip():
                self.statusBar().showMessage(result.message(), 3000)
            return

        self.statusBar().showMessage(result.message())
        if result.single is not None:
            self.results.hide()
            self._show_hit(result.single, animate=True)
            return
        if result.hits:
            self.results.show_hits(result.hits)
            self._show_hit(result.hits[0], animate=True)
        elif result.suggestions:
            self.results.show_hits(result.suggestions, suggestion=True)
        else:
            self.results.hide()
            self.result_card.clear()
            self.viewer.clear_highlight()
            return
        self._place_results_popup()

    def _place_results_popup(self) -> None:
        box = self.search_bar.box
        top_left = box.mapToGlobal(QPoint(0, box.height() + 6))
        height = min(430, max(90, self.results.sizeHintForRow(0) * self.results.count() + 16))
        self.results.setGeometry(top_left.x(), top_left.y(), box.width(), height)
        self.results.show()
        self.search_bar.box.setFocus()

    def _move_selection(self, delta: int) -> None:
        if not self.results.isVisible() or self.results.count() == 0:
            return
        row = (self.results.currentRow() + delta) % self.results.count()
        self.results.setCurrentRow(row)

    def _open_top_result(self) -> None:
        if self.results.isVisible() and self.results.currentItem() is not None:
            self.results.itemActivated.emit(self.results.currentItem())
            return
        result = self.library.search(self.search_bar.text(),
                                     layout_ids=self.search_bar.scope_ids())
        if result.hits:
            self._open_hit(result.hits[0])

    def _open_hit(self, hit) -> None:
        self.results.hide()
        self._show_hit(hit, animate=True)

    def _show_hit(self, hit, animate: bool = True) -> None:
        page, product = hit.page, hit.product
        if self._current_page is None or self._current_page.id != page.id:
            self.open_page(page, hit.layout)
        self.result_card.show_location(locate(product, page, hit.layout))
        self.viewer.highlight(product, animate=animate)

    def _clear_search(self) -> None:
        self.results.hide()
        self.search_bar.clear()
        self.viewer.clear_highlight()
        self.result_card.clear()
        self.statusBar().showMessage("Ready", 2000)

    def _clicked_on_page(self, point) -> None:
        """Reverse lookup: clicking a product on the sheet shows its card."""
        if self._current_page is None:
            return
        product = self.library.product_at(self._current_page, point[0], point[1])
        if product is None:
            return
        layout = self._current_layout or self.library.layout_of(self._current_page)
        if layout is None:
            return
        self.result_card.show_location(locate(product, self._current_page, layout))
        self.viewer.highlight(product, animate=True, zoom=False)
        self.statusBar().showMessage(f"{product.code} {product.name}".strip(), 6000)

    # ------------------------------------------------------- importing
    def choose_files(self) -> None:
        patterns = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose layout sheets", "",
                                                f"Layout sheets ({patterns});;All files (*)")
        if paths:
            self.start_import(paths)

    def start_import(self, paths: list[str]) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "Import running",
                                    "One import is already running - let it finish first.")
            return
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.import_button.setEnabled(False)
        self.statusBar().showMessage("Reading sheets...")

        worker = ImportWorker(self.library, paths, self)
        worker.progressed.connect(self._import_progress)
        worker.completed.connect(self._import_done)
        worker.failed.connect(self._import_failed)
        worker.finished.connect(lambda: self.import_button.setEnabled(True))
        self._worker = worker
        worker.start()

    def _import_progress(self, progress) -> None:
        self.progress.setValue(int(progress.fraction * 100))
        self.statusBar().showMessage(describe(progress))

    def _import_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.import_button.setEnabled(True)
        QMessageBox.warning(self, "Import failed", message)

    def _import_done(self, report: ImportReport) -> None:
        self.progress.setVisible(False)
        self.import_button.setEnabled(True)
        if not report.pages:
            QMessageBox.warning(self, "Nothing imported",
                                "No sheets could be read from those files."
                                + ("\n\n" + "\n".join(f"{os.path.basename(path)}: {reason}"
                                                      for path, reason in report.failures)
                                   if report.failures else ""))
            return

        mode = self._ask_about_existing(report)
        if mode is None:
            self.statusBar().showMessage("Import cancelled", 4000)
            return
        self.library.commit(report, default_mode=mode)
        self.refresh_library()

        first = report.pages[0]
        stored_page = self._find_stored_page(first.id)
        if stored_page is not None:
            self.open_page(stored_page)

        warnings = report.warnings()
        message = describe_report(report)
        if warnings:
            box = QMessageBox(self)
            box.setWindowTitle("Imported with notes")
            box.setText(f"Imported {message}.")
            box.setInformativeText("Some pages need a look:")
            box.setDetailedText("\n".join(warnings))
            box.exec()
        self.statusBar().showMessage(f"Imported {message}", 8000)

    def _find_stored_page(self, page_id: str) -> Optional[Page]:
        for layout in self.library.layouts:
            for page in layout.pages:
                if page.id == page_id:
                    return page
        return None

    def _ask_about_existing(self, report: ImportReport) -> Optional[ImportMode]:
        conflicts = self.library.conflicts(report)
        if not conflicts:
            return ImportMode.KEEP_BOTH

        lines = []
        for conflict in conflicts:
            for existing in conflict.existing:
                lines.append(f"{existing.title}: {existing.page_count} page(s), "
                             f"imported {existing.imported_at[:16].replace('T', ' ')}")
        box = QMessageBox(self)
        box.setWindowTitle("That layout is already here")
        box.setText("A layout with the same name and size is already stored.")
        box.setInformativeText("\n".join(lines))
        replace = box.addButton("Replace it", QMessageBox.ButtonRole.DestructiveRole)
        merge = box.addButton("Update these pages", QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton("Keep both", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is replace:
            return ImportMode.REPLACE
        if clicked is merge:
            return ImportMode.MERGE_PAGES
        if clicked is keep:
            return ImportMode.KEEP_BOTH
        return None

    # ------------------------------------------------------------ review
    def review_current_page(self) -> None:
        """Open the page for checking and correcting."""

        if self._current_page is None:
            self.statusBar().showMessage("Open a page first", 4000)
            return
        path = self.library.page_image_path(self._current_page)
        if not path:
            QMessageBox.information(self, "No picture for this page",
                                    "The straightened image for this page is missing, so "
                                    "there is nothing to review against.")
            return

        dialog = ReviewDialog(self._current_page, path, self)
        dialog.pageSaved.connect(self._save_reviewed_page)
        dialog.exec()

    def _save_reviewed_page(self, page: Page) -> None:
        try:
            self.library.save_page(page)
        except ValueError as error:
            QMessageBox.warning(self, "Could not save", str(error))
            return
        self.refresh_library()
        stored = self._find_stored_page(page.id)
        if stored is not None:
            self.open_page(stored, keep_view=True)
        summary = editing.review_summary(page)
        self.statusBar().showMessage(f"Saved. {summary.describe()}", 8000)

    # ------------------------------------------------------- layout packs
    def export_pack(self) -> None:
        """Write a layout to a pack the phone app - or another PC - can read."""

        layouts = self.library.layouts
        if not layouts:
            QMessageBox.information(self, "Nothing to export",
                                    "Import some sheets first.")
            return

        choices = ["Everything"] + [layout.title or "Untitled layout" for layout in layouts]
        current = 0
        if self._current_layout is not None:
            for index, layout in enumerate(layouts, start=1):
                if layout.id == self._current_layout.id:
                    current = index
                    break
        choice, accepted = QInputDialog.getItem(self, "Export a layout pack",
                                                "Which layout?", choices, current, False)
        if not accepted:
            return
        layout_ids = None
        if choice != "Everything":
            layout_ids = [layout.id for layout in layouts
                          if (layout.title or "Untitled layout") == choice]

        suggested = (choice if choice != "Everything" else "shelffinder").replace(" ", "-")
        path, _ = QFileDialog.getSaveFileName(self, "Save the layout pack",
                                              f"{suggested}.shelfpack.zip",
                                              "Layout pack (*.zip)")
        if not path:
            return

        self.statusBar().showMessage("Writing the pack...")
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        try:
            summary = self.library.export_pack(path, layout_ids=layout_ids)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Could not write the pack", str(error))
            self.statusBar().showMessage("Export failed", 5000)
            return
        finally:
            QApplication.restoreOverrideCursor()

        QMessageBox.information(
            self, "Pack written",
            f"{os.path.basename(path)}\n\n{summary.describe()}\n\n"
            "Copy it to the phone and open it with ShelfFinder for Android.")
        self.statusBar().showMessage(f"Exported {summary.describe()}", 8000)

    def import_pack(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open a layout pack", "",
                                              "Layout pack (*.zip);;All files (*)")
        if not path:
            return
        try:
            self.library.import_pack(path)
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.warning(self, "Could not read that pack", str(error))
            return
        self.refresh_library(select_first=True)
        self.statusBar().showMessage(f"Imported {os.path.basename(path)}", 8000)

    # ------------------------------------------------------- drag and drop
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        packs = [path for path in paths if path.lower().endswith(".zip")]
        if packs:
            for pack in packs:
                try:
                    self.library.import_pack(pack)
                except (OSError, ValueError, KeyError) as error:
                    QMessageBox.warning(self, "Could not read that pack", str(error))
                    return
            self.refresh_library(select_first=True)
            self.statusBar().showMessage(f"Imported {len(packs)} pack(s)", 8000)
            event.acceptProposedAction()
            return

        supported = [path for path in paths
                     if os.path.isdir(path)
                     or os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS]
        if supported:
            self.start_import(supported)
            event.acceptProposedAction()
        else:
            self.statusBar().showMessage("Those files are not layout sheets", 5000)

    # ------------------------------------------------------- narrow windows
    def apply_responsive_layout(self, width: int) -> None:
        """Stack the panels when the window is too narrow to sit them side by side."""

        narrow = width < NARROW_WIDTH
        wanted = Qt.Orientation.Vertical if narrow else Qt.Orientation.Horizontal
        if self.splitter.orientation() != wanted:
            self.splitter.setOrientation(wanted)
            self.splitter.setSizes([250, 900, 340] if not narrow else [150, 640, 270])
        if width < 820 and not self.sidebar_holder.isHidden():
            self.sidebar_holder.setVisible(False)
            self.sidebar_button.setChecked(False)
        elif width >= 820 and self.settings.sidebar_visible and \
                self.sidebar_holder.isHidden():
            self.sidebar_holder.setVisible(True)
            self.sidebar_button.setChecked(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.apply_responsive_layout(self.width())

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self.settings.save()
        self.library.close()
        super().closeEvent(event)
