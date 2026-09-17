"""Settings: highlight colour, dim level, default search scope, data folder."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSlider, QVBoxLayout)

from .settings import AppSettings
from . import theme


class _ColourButton(QPushButton):
    def __init__(self, colour: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(110)
        self._colour = colour
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self) -> None:
        self.setText(self._colour.upper())
        readable = "#0B1020" if QColor(self._colour).lightnessF() > 0.55 else theme.TEXT
        self.setStyleSheet(f"background: {self._colour}; color: {readable};"
                           f" border: 1px solid {theme.BORDER};"
                           f" border-radius: {theme.RADIUS}px; padding: 7px 14px;")

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._colour), self, "Pick a colour")
        if chosen.isValid():
            self._colour = chosen.name()
            self._refresh()

    def colour(self) -> str:
        return self._colour


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, layouts, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        self._settings = settings

        outer = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        self.highlight = _ColourButton(settings.highlight_colour, self)
        form.addRow("Highlight colour", self.highlight)
        self.accent = _ColourButton(settings.accent_colour, self)
        form.addRow("Accent colour", self.accent)

        dim_row = QHBoxLayout()
        self.dim = QSlider(Qt.Orientation.Horizontal, self)
        self.dim.setRange(0, 90)
        self.dim.setValue(settings.dim_level)
        self.dim_value = QLabel(f"{settings.dim_level}%")
        self.dim.valueChanged.connect(lambda value: self.dim_value.setText(f"{value}%"))
        dim_row.addWidget(self.dim, 1)
        dim_row.addWidget(self.dim_value)
        form.addRow("Dim the rest of the page", dim_row)

        self.scope = QComboBox(self)
        self.scope.addItem("All layouts", "all")
        for layout in layouts:
            self.scope.addItem(layout.title or "Untitled layout", layout.id)
        index = self.scope.findData(settings.default_scope)
        self.scope.setCurrentIndex(max(index, 0))
        form.addRow("Search by default in", self.scope)

        folder_row = QHBoxLayout()
        self.folder = QLineEdit(settings.data_dir, self)
        self.folder.setReadOnly(True)
        browse = QPushButton("Change...", self)
        browse.clicked.connect(self._browse)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        form.addRow("Data folder", folder_row)

        outer.addLayout(form)
        note = QLabel("Sheets and the database stay on this machine. Moving the data "
                      "folder copies everything across.")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        outer.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose a data folder",
                                                  self.folder.text())
        if chosen:
            self.folder.setText(chosen)

    def result_settings(self) -> AppSettings:
        return self._settings.with_changes(
            highlight_colour=self.highlight.colour(),
            accent_colour=self.accent.colour(),
            dim_level=self.dim.value(),
            default_scope=self.scope.currentData() or "all",
            data_dir=self.folder.text(),
        )
