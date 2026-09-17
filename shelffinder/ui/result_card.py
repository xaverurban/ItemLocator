"""The result card: big numbers, readable at arm's length on the shop floor."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout,
                               QWidget)

from ..core.locate import Location
from . import theme


def _label(text: str, size: int, weight: int = 400, colour: str = theme.TEXT,
           wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(wrap)
    label.setStyleSheet(f"color: {colour}; font-size: {size}px; font-weight: {weight};"
                        " background: transparent;")
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class _Stat(QFrame):
    """One big number with a caption under it."""

    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 10, 12, 10)
        box.setSpacing(2)
        self.value = _label("-", 30, 700)
        self.caption = _label(caption.upper(), 11, 600, theme.TEXT_DIM)
        self.detail = _label("", 12, 400, theme.TEXT_DIM, wrap=True)
        box.addWidget(self.value)
        box.addWidget(self.caption)
        box.addWidget(self.detail)

    def set(self, value: str, detail: str = "") -> None:
        self.value.setText(value)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))


class ResultCard(QWidget):
    """Where one product goes, in numbers a worker can read from a metre away."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        header = QFrame()
        header.setObjectName("Panel")
        header_box = QVBoxLayout(header)
        header_box.setContentsMargins(14, 12, 14, 12)
        header_box.setSpacing(4)
        self.code = _label("", 38, 700)
        self.name = _label("", 16, 500, theme.TEXT, wrap=True)
        self.where = _label("", 13, 400, theme.TEXT_DIM, wrap=True)
        header_box.addWidget(self.code)
        header_box.addWidget(self.name)
        header_box.addWidget(self.where)
        outer.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.bay = _Stat("Bay")
        self.shelf = _Stat("Shelf from top")
        self.position = _Stat("Position from left")
        self.cases = _Stat("Cases")
        grid.addWidget(self.bay, 0, 0)
        grid.addWidget(self.shelf, 0, 1)
        grid.addWidget(self.position, 1, 0)
        grid.addWidget(self.cases, 1, 1)
        outer.addLayout(grid)

        neighbours = QFrame()
        neighbours.setObjectName("Panel")
        neighbour_box = QVBoxLayout(neighbours)
        neighbour_box.setContentsMargins(14, 12, 14, 12)
        neighbour_box.setSpacing(6)
        neighbour_box.addWidget(_label("NEIGHBOURS", 11, 600, theme.TEXT_DIM))
        self.left_neighbour = _label("-", 13, 400, theme.TEXT, wrap=True)
        self.right_neighbour = _label("-", 13, 400, theme.TEXT, wrap=True)
        neighbour_box.addWidget(self.left_neighbour)
        neighbour_box.addWidget(self.right_neighbour)
        outer.addWidget(neighbours)

        self.warning = _label("", 12, 500, theme.AMBER, wrap=True)
        self.warning.setVisible(False)
        outer.addWidget(self.warning)

        self.tip = _label(
            "Ambient layouts: the first visible notch above the plinth is notch 4. "
            "Chiller layouts: the first visible notch above the base is notch 1.",
            11, 400, theme.TEXT_FAINT, wrap=True)
        outer.addWidget(self.tip)
        outer.addStretch(1)

        self._placeholder()

    def _placeholder(self) -> None:
        self.code.setText("-")
        self.name.setText("Search a code to see where it goes.")
        self.where.setText("")
        for stat, caption in ((self.bay, "Bay"), (self.shelf, "Shelf from top"),
                              (self.position, "Position from left"), (self.cases, "Cases")):
            stat.set("-")
            stat.caption.setText(caption.upper())
        self.left_neighbour.setText("-")
        self.right_neighbour.setText("-")
        self.warning.setVisible(False)

    def clear(self) -> None:
        self._placeholder()

    def show_location(self, card: Optional[Location]) -> None:
        if card is None:
            self._placeholder()
            return

        self.code.setText(card.code or "(no code)")
        self.name.setText(card.name or "(name not read)")
        self.where.setText(card.page_label())

        self.bay.set(f"{card.bay_index}", f"of {card.bay_count} in customer-flow order")
        self.shelf.set(f"{card.shelf_from_top}",
                       f"{card.shelf_from_bottom} from bottom · {card.notch_label()}"
                       if card.shelf_from_bottom else card.notch_label())
        self.position.set(f"{card.position_left}",
                          f"{card.position_right} from right of {card.position_count}"
                          " on this shelf")
        self.cases.set("-" if card.cases is None else str(card.cases))

        left = card.neighbour_left
        right = card.neighbour_right
        self.left_neighbour.setText(f"← {left.describe()}" if left else "← nothing to the left")
        self.right_neighbour.setText(f"→ {right.describe()}" if right
                                     else "→ nothing to the right")

        notes = []
        if card.product.confidence < 0.72:
            notes.append("read with low confidence")
        if "unreadable" in card.product.tags:
            notes.append("the label could not be read")
        if not card.product.name:
            notes.append("no name was read")
        if card.bay is not None and card.bay.shelves_inherited:
            notes.append(f"bay {card.bay_index} has no notch line of its own, so it uses "
                         "the shelves of the bay before it")
        if card.product.manually_edited:
            notes.append("checked by hand")
        self.warning.setText("! " + "; ".join(notes) if notes else "")
        self.warning.setVisible(bool(notes) and not (
            len(notes) == 1 and card.product.manually_edited))
