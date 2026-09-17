"""Left sidebar (layouts and their pages) and the page thumbnail strip."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QLabel, QListWidget, QListWidgetItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core.models import Layout, Page
from . import theme

ROLE_PAGE = Qt.ItemDataRole.UserRole + 1
ROLE_LAYOUT = Qt.ItemDataRole.UserRole + 2


class LayoutSidebar(QWidget):
    """Layouts, their pages, and which one is open."""

    pageSelected = Signal(object, object)          # page, layout
    layoutDeleteRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)

        heading = QLabel("LAYOUTS")
        heading.setObjectName("Heading")
        box.addWidget(heading)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.currentItemChanged.connect(self._changed)
        box.addWidget(self.tree, 1)

        self.summary = QLabel("")
        self.summary.setObjectName("Hint")
        self.summary.setWordWrap(True)
        box.addWidget(self.summary)

    def set_layouts(self, layouts: list[Layout], current_page_id: str = "") -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        pages = products = 0
        for layout in layouts:
            parent = QTreeWidgetItem([layout.title or "Untitled layout"])
            parent.setData(0, ROLE_LAYOUT, layout)
            parent.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(parent)
            for page in layout.pages:
                pages += 1
                products += len(page.products)
                total = f"/{page.total_pages}" if page.total_pages else ""
                child = QTreeWidgetItem([f"Page {page.number}{total}"
                                         f"  ·  {len(page.products)}"])
                child.setData(0, ROLE_PAGE, page)
                child.setData(0, ROLE_LAYOUT, layout)
                tooltip = [f"Page {page.number}{total}, {len(page.products)} products",
                           *page.warnings]
                child.setToolTip(0, "\n".join(tooltip))
                if page.warnings:
                    child.setForeground(0, Qt.GlobalColor.yellow)
                parent.addChild(child)
                if page.id == current_page_id:
                    self.tree.setCurrentItem(child)
            parent.setExpanded(True)
        self.tree.blockSignals(False)
        self.summary.setText(f"{len(layouts)} layout(s), {pages} page(s), {products} products")

    def _changed(self, current: Optional[QTreeWidgetItem], _previous) -> None:
        if current is None:
            return
        page = current.data(0, ROLE_PAGE)
        layout = current.data(0, ROLE_LAYOUT)
        if page is not None:
            self.pageSelected.emit(page, layout)

    def select_page(self, page: Page) -> None:
        for index in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(index)
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                stored = child.data(0, ROLE_PAGE)
                if stored is not None and stored.id == page.id:
                    self.tree.blockSignals(True)
                    self.tree.setCurrentItem(child)
                    self.tree.blockSignals(False)
                    return

    def current_layout_id(self) -> Optional[str]:
        item = self.tree.currentItem()
        if item is None:
            return None
        layout = item.data(0, ROLE_LAYOUT)
        return layout.id if layout is not None else None


class ThumbnailStrip(QListWidget):
    """Pages of the current layout, along the bottom of the viewer."""

    pageChosen = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Thumbnails")
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(74, 104))
        self.setGridSize(QSize(102, 138))
        self.setFixedHeight(152)
        self.setSpacing(6)
        self.setUniformItemSizes(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMovement(QListWidget.Movement.Static)
        self.itemClicked.connect(self._chosen)
        self._cache: dict[str, QIcon] = {}

    def _chosen(self, item: QListWidgetItem) -> None:
        page = item.data(ROLE_PAGE)
        if page is not None:
            self.pageChosen.emit(page)

    def set_pages(self, layout: Optional[Layout], resolve, current_page_id: str = "") -> None:
        self.clear()
        if layout is None or not layout.pages:
            self.setVisible(False)
            return
        self.setVisible(len(layout.pages) > 1)
        for page in layout.pages:
            item = QListWidgetItem(f"Page {page.number}")
            item.setData(ROLE_PAGE, page)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            icon = self._icon(page, resolve)
            if icon is not None:
                item.setIcon(icon)
            self.addItem(item)
            if page.id == current_page_id:
                self.setCurrentItem(item)

    def _icon(self, page: Page, resolve) -> Optional[QIcon]:
        if page.id in self._cache:
            return self._cache[page.id]
        path = resolve(page)
        if not path or not os.path.exists(path):
            return None
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return None
        icon = QIcon(pixmap.scaled(QSize(148, 208), Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
        self._cache[page.id] = icon
        return icon

    def select_page(self, page: Page) -> None:
        for index in range(self.count()):
            item = self.item(index)
            stored = item.data(ROLE_PAGE)
            if stored is not None and stored.id == page.id:
                self.setCurrentItem(item)
                return
