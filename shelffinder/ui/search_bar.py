"""The search box, its debounce, and the result list that drops out of it."""

from __future__ import annotations

import html
from typing import Optional, Sequence

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QWidget)

from ..core.locate import locate_hit
from ..core.search import SearchHit
from . import theme

DEBOUNCE_MS = 150
ROLE_HTML = Qt.ItemDataRole.UserRole + 1
ROLE_HIT = Qt.ItemDataRole.UserRole + 2


class _RichTextDelegate(QStyledItemDelegate):
    """Draws the result rows, with the digits you typed in bold."""

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        painter.save()
        style = options.widget.style() if options.widget else QStyle()
        options.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, options, painter,
                          options.widget)
        document = QTextDocument()
        selected = bool(options.state & QStyle.StateFlag.State_Selected)
        body = "#0B1020" if selected else theme.TEXT
        secondary = "#0B1020" if selected else theme.TEXT_DIM
        matched = "#26324D" if selected else theme.DEFAULT_HIGHLIGHT
        document.setDefaultStyleSheet(
            f"body {{ color: {body}; font-size: 14px; }} "
            f".dim {{ color: {secondary}; font-size: 12px; }} "
            f"b {{ color: {matched}; }}")
        document.setHtml(index.data(ROLE_HTML) or "")
        document.setTextWidth(options.rect.width() - 16)
        painter.translate(options.rect.left() + 8, options.rect.top() + 6)
        document.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        document = QTextDocument()
        document.setHtml(index.data(ROLE_HTML) or "")
        document.setTextWidth(option.rect.width() - 16 if option.rect.width() > 40 else 320)
        return QSize(int(document.idealWidth()) + 16, int(document.size().height()) + 12)


class ResultList(QListWidget):
    """The list of matches; also used as a popup under the search box."""

    hitChosen = Signal(object)
    hitHighlighted = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Results")
        self.setItemDelegate(_RichTextDelegate(self))
        self.setUniformItemSizes(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.itemActivated.connect(self._chosen)
        self.itemClicked.connect(self._chosen)
        self.currentItemChanged.connect(self._current_changed)

    def _chosen(self, item: QListWidgetItem) -> None:
        hit = item.data(ROLE_HIT)
        if hit is not None:
            self.hitChosen.emit(hit)

    def _current_changed(self, current: Optional[QListWidgetItem], _previous) -> None:
        if current is not None:
            hit = current.data(ROLE_HIT)
            if hit is not None:
                self.hitHighlighted.emit(hit)

    def show_hits(self, hits: Sequence[SearchHit], suggestion: bool = False) -> None:
        self.clear()
        for hit in hits:
            item = QListWidgetItem()
            item.setData(ROLE_HTML, self._row_html(hit, suggestion))
            item.setData(ROLE_HIT, hit)
            self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    @staticmethod
    def _row_html(hit: SearchHit, suggestion: bool) -> str:
        before, matched, after = hit.highlight()
        code = f"{html.escape(before)}<b>{html.escape(matched)}</b>{html.escape(after)}"
        card = locate_hit(hit)
        name = html.escape(hit.product.name or "(no name read)")
        where = html.escape(f"{card.page_label()} · {card.bay_label()} · "
                            f"shelf {card.shelf_from_top} · position {card.position_left}")
        prefix = f"<span class='dim'>{html.escape(hit.reason)} - </span>" if suggestion else ""
        return (f"<body>{prefix}<span style='font-size:16px;font-weight:600'>{code}</span>"
                f" &nbsp;{name}<br><span class='dim'>{where}</span></body>")


class SearchBar(QWidget):
    """Digits-only search with a 150 ms debounce and a layout scope."""

    queryChanged = Signal(str, object)      # text, layout_ids or None
    submitted = Signal()
    escaped = Signal()
    navigate = Signal(int)                  # -1 up, +1 down

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.box = QLineEdit(self)
        self.box.setObjectName("SearchBox")
        self.box.setPlaceholderText("Search product code")
        self.box.setClearButtonEnabled(True)
        self.box.installEventFilter(self)
        layout.addWidget(self.box, 1)

        self.scope = QComboBox(self)
        self.scope.setMinimumWidth(190)
        self.scope.addItem("All layouts", None)
        self.scope.currentIndexChanged.connect(lambda _: self._emit())
        layout.addWidget(self.scope)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._emit)
        self.box.textChanged.connect(lambda _: self._timer.start())

    # -- scope ------------------------------------------------------------
    def set_layouts(self, layouts, selected_id: str = "all") -> None:
        current = self.current_scope_id()
        self.scope.blockSignals(True)
        self.scope.clear()
        self.scope.addItem("All layouts", None)
        for layout in layouts:
            self.scope.addItem(layout.title or "Untitled layout", layout.id)
        wanted = selected_id if current in (None, "all") else current
        if wanted and wanted != "all":
            index = self.scope.findData(wanted)
            if index >= 0:
                self.scope.setCurrentIndex(index)
        self.scope.blockSignals(False)

    def current_scope_id(self) -> Optional[str]:
        return self.scope.currentData()

    def scope_ids(self) -> Optional[list[str]]:
        layout_id = self.current_scope_id()
        return [layout_id] if layout_id else None

    # -- text -------------------------------------------------------------
    def text(self) -> str:
        return self.box.text()

    def clear(self) -> None:
        self.box.clear()

    def focus(self) -> None:
        self.box.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.box.selectAll()

    def _emit(self) -> None:
        self._timer.stop()
        self.queryChanged.emit(self.box.text(), self.scope_ids())

    def eventFilter(self, watched, event):
        if watched is self.box and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self.navigate.emit(1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._timer.stop()
                self._emit()
                self.submitted.emit()
                return True
            if key == Qt.Key.Key_Escape:
                self.escaped.emit()
                return True
        return super().eventFilter(watched, event)
