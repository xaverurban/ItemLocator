"""The review screen: check what was read, fix what was not, then save."""

from __future__ import annotations

import copy
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QFormLayout, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import editing
from ..core.models import BBox, Page, Product
from . import theme
from .review_canvas import ReviewCanvas

COLUMNS = ("Code", "Name", "Cases", "Bay", "Shelf", "Pos")


class ReviewDialog(QDialog):
    """Everything on one page, editable, with a save that search then relies on."""

    pageSaved = Signal(object)          # the saved Page

    def __init__(self, page: Page, image_path: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Review page {page.number}")
        self.resize(1500, 950)
        self.setSizeGripEnabled(True)

        # Work on a copy: Cancel has to leave the stored page untouched.
        self.page = Page.from_dict(copy.deepcopy(page.to_dict()))
        self.page.id = page.id
        self._image_path = image_path
        self._loading = False

        self._build_ui()
        self.canvas.show_page(self.page, image_path)
        self._refresh_table()
        self._refresh_summary()

        QShortcut(QKeySequence("Delete"), self, self.delete_selected)
        QShortcut(QKeySequence("Ctrl+N"), self, self.start_adding)
        QShortcut(QKeySequence("Ctrl+S"), self, self.accept)

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        self.summary = QLabel("")
        self.summary.setObjectName("Heading")
        header.addWidget(self.summary, 1)

        self.only_flagged = QCheckBox("Only what needs checking")
        self.only_flagged.stateChanged.connect(lambda _: self._refresh_table())
        header.addWidget(self.only_flagged)

        add_button = QPushButton("Add product (Ctrl+N)")
        add_button.clicked.connect(self.start_adding)
        header.addWidget(add_button)

        self.delete_button = QPushButton("Delete (Del)")
        self.delete_button.clicked.connect(self.delete_selected)
        self.delete_button.setEnabled(False)
        header.addWidget(self.delete_button)

        fit_button = QPushButton("Fit page")
        fit_button.clicked.connect(lambda: self.canvas.fit_page())
        header.addWidget(fit_button)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        self.canvas = ReviewCanvas(self)
        self.canvas.selectionChanged.connect(self._canvas_selection)
        self.canvas.boxMoved.connect(self._box_moved)
        self.canvas.guideMoved.connect(self._guide_moved)
        self.canvas.drawFinished.connect(self._draw_finished)
        splitter.addWidget(self.canvas)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._table_selection)
        side_layout.addWidget(self.table, 1)

        side_layout.addWidget(self._build_product_form())
        side_layout.addWidget(self._build_shelf_form())
        self._set_product_form_enabled(False)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Save this page")
        save.setObjectName("Primary")
        save.clicked.connect(self.accept)
        buttons.addWidget(save)
        side_layout.addLayout(buttons)

        side.setMinimumWidth(420)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1000, 470])
        outer.addWidget(splitter, 1)

    def _build_product_form(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("SELECTED PRODUCT")
        title.setObjectName("Heading")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)
        self.code_field = QLineEdit()
        self.code_field.setPlaceholderText("digits only")
        self.code_field.editingFinished.connect(self._apply_product_edits)
        form.addRow("Code", self.code_field)

        self.name_field = QLineEdit()
        self.name_field.editingFinished.connect(self._apply_product_edits)
        form.addRow("Name", self.name_field)

        self.cases_field = QSpinBox()
        self.cases_field.setRange(0, 999)
        self.cases_field.setSpecialValueText("not read")
        self.cases_field.editingFinished.connect(self._apply_product_edits)
        form.addRow("Cases", self.cases_field)
        layout.addLayout(form)

        self.placement = QLabel("")
        self.placement.setObjectName("Hint")
        self.placement.setWordWrap(True)
        layout.addWidget(self.placement)
        return frame

    def _build_shelf_form(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("ITS SHELF")
        title.setObjectName("Heading")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)
        self.notch_field = QSpinBox()
        self.notch_field.setRange(0, 99)
        self.notch_field.setSpecialValueText("not read")
        self.notch_field.editingFinished.connect(self._apply_shelf_edits)
        form.addRow("Notch", self.notch_field)

        self.depth_field = QSpinBox()
        self.depth_field.setRange(0, 200)
        self.depth_field.setSuffix(" cm")
        self.depth_field.setSpecialValueText("not read")
        self.depth_field.editingFinished.connect(self._apply_shelf_edits)
        form.addRow("Depth", self.depth_field)

        self.slope_field = QSpinBox()
        self.slope_field.setRange(-20, 20)
        self.slope_field.editingFinished.connect(self._apply_shelf_edits)
        form.addRow("Slope", self.slope_field)
        layout.addLayout(form)

        self.shelf_note = QLabel("")
        self.shelf_note.setObjectName("Hint")
        self.shelf_note.setWordWrap(True)
        layout.addWidget(self.shelf_note)
        return frame

    # -------------------------------------------------------------- refresh
    def _refresh_summary(self) -> None:
        summary = editing.review_summary(self.page)
        self.summary.setText(summary.describe().upper())
        colour = theme.GREEN if summary.is_clean else theme.AMBER
        self.summary.setStyleSheet(f"color: {colour}; font-weight: 600;")

    def _visible_products(self) -> list[Product]:
        products = sorted(self.page.products,
                          key=lambda p: (p.bay, p.shelf, p.position_left))
        if self.only_flagged.isChecked():
            products = [p for p in products if editing.needs_checking(p)]
        return products

    def _refresh_table(self) -> None:
        self._loading = True
        products = self._visible_products()
        self.table.setRowCount(len(products))
        for row, product in enumerate(products):
            values = [product.code or "(no code)", product.name or "(no name)",
                      "-" if product.cases is None else str(product.cases),
                      str(product.bay), str(product.shelf), str(product.position_left)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, product.id)
                if editing.needs_checking(product):
                    item.setForeground(QColor(theme.AMBER))
                elif product.manually_edited:
                    item.setForeground(QColor(theme.GREEN))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._loading = False

    def _set_product_form_enabled(self, enabled: bool) -> None:
        for widget in (self.code_field, self.name_field, self.cases_field):
            widget.setEnabled(enabled)
        for widget in (self.notch_field, self.depth_field, self.slope_field):
            widget.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def _show_product(self, product: Optional[Product]) -> None:
        self._loading = True
        if product is None:
            self.code_field.clear()
            self.name_field.clear()
            self.cases_field.setValue(0)
            self.placement.setText("Pick a product on the page or in the list.")
            self.shelf_note.setText("")
            self._set_product_form_enabled(False)
            self._loading = False
            return

        self._set_product_form_enabled(True)
        self.code_field.setText(product.code)
        self.name_field.setText(product.name)
        self.cases_field.setValue(product.cases or 0)

        notes = []
        if editing.needs_checking(product):
            notes.append("needs checking")
        if product.manually_edited:
            notes.append("checked by hand")
        if product.tags:
            notes.append(", ".join(product.tags))
        self.placement.setText(
            f"Bay {product.bay}, shelf {product.shelf}, position {product.position_left} "
            f"(read at {product.confidence:.0%})"
            + (f" - {'; '.join(notes)}" if notes else ""))

        shelf = self.page.shelf_of(product)
        bay = self.page.bay_of(product)
        self.notch_field.setValue(shelf.notch or 0 if shelf else 0)
        self.depth_field.setValue(int(shelf.depth_cm or 0) if shelf else 0)
        self.slope_field.setValue(int(shelf.slope or 0) if shelf else 0)
        if shelf is None:
            self.shelf_note.setText("This product is not on a shelf yet.")
        elif bay is not None and bay.shelves_inherited:
            self.shelf_note.setText(
                f"Bay {bay.index} has no notch line of its own - these shelves came from "
                f"the bay to its left. Editing them makes them this bay's own.")
        else:
            self.shelf_note.setText("")
        self._loading = False

    # ------------------------------------------------------------- editing
    def _canvas_selection(self, product: Optional[Product]) -> None:
        self._show_product(product)
        if product is None or self._loading:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == product.id:
                self.table.blockSignals(True)
                self.table.selectRow(row)
                self.table.blockSignals(False)
                break

    def _table_selection(self) -> None:
        if self._loading:
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        product_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        product = next((p for p in self.page.products if p.id == product_id), None)
        self.canvas.select_product(product)
        self._show_product(product)

    def _current_product(self) -> Optional[Product]:
        return self.canvas.selected_product()

    def _apply_product_edits(self) -> None:
        if self._loading:
            return
        product = self._current_product()
        if product is None:
            return
        cases = self.cases_field.value()
        editing.update_product(
            self.page, product,
            code=self.code_field.text(),
            name=self.name_field.text(),
            cases=None if cases == 0 else cases,
        )
        self.canvas.rebuild()
        self.canvas.select_product(product)
        self._refresh_table()
        self._refresh_summary()
        self._show_product(product)

    def _apply_shelf_edits(self) -> None:
        if self._loading:
            return
        product = self._current_product()
        if product is None or not product.bay or not product.shelf:
            return
        notch = self.notch_field.value()
        depth = self.depth_field.value()
        editing.update_shelf(self.page, product.bay, product.shelf,
                             notch=None if notch == 0 else notch,
                             depth_cm=None if depth == 0 else float(depth),
                             slope=float(self.slope_field.value()))
        self._refresh_summary()
        self._show_product(product)

    def _box_moved(self, product: Product, box: BBox) -> None:
        editing.update_product(self.page, product, bbox=box)
        self.canvas.rebuild()
        self.canvas.select_product(product)
        self._refresh_table()
        self._refresh_summary()
        self._show_product(product)

    def _guide_moved(self, guide) -> None:
        try:
            if guide.vertical:
                editing.set_bay_edges(self.page, self.canvas.bay_edges())
            else:
                editing.set_shelf_edges(self.page, guide.bay_index,
                                        self.canvas.shelf_edges(guide.bay_index))
        except ValueError as error:
            QMessageBox.warning(self, "That line cannot go there", str(error))
        self.canvas.rebuild()
        self._refresh_table()
        self._refresh_summary()
        self._show_product(self._current_product())

    def start_adding(self) -> None:
        self.canvas.start_drawing()
        self.summary.setText("DRAW A BOX ROUND THE LABEL YOU WANT TO ADD")

    def _draw_finished(self, box: BBox) -> None:
        product = editing.add_product(self.page, box)
        self.canvas.rebuild()
        self.canvas.select_product(product)
        self._refresh_table()
        self._refresh_summary()
        self._show_product(product)
        self.code_field.setFocus()
        self.code_field.selectAll()

    def delete_selected(self) -> None:
        product = self._current_product()
        if product is None:
            return
        editing.delete_product(self.page, product)
        self.canvas.rebuild()
        self._refresh_table()
        self._refresh_summary()
        self._show_product(None)

    # -------------------------------------------------------------- saving
    def accept(self) -> None:
        self.page.warnings = [warning for warning in self.page.warnings
                              if "need checking" not in warning]
        summary = editing.review_summary(self.page)
        if summary.needs_checking:
            self.page.warnings.append(
                f"{summary.needs_checking} of {summary.total} products still need checking.")
        self.pageSaved.emit(self.page)
        super().accept()
