"""User settings, persisted with QSettings."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from PySide6.QtCore import QSettings, QStandardPaths

from .theme import DEFAULT_ACCENT, DEFAULT_HIGHLIGHT

ORGANISATION = "ShelfFinder"
APPLICATION = "ShelfFinder"


def default_data_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".shelffinder")
    return os.path.join(base, "library")


@dataclass
class AppSettings:
    highlight_colour: str = DEFAULT_HIGHLIGHT
    accent_colour: str = DEFAULT_ACCENT
    dim_level: int = 50                 # percent the rest of the page is dimmed
    default_scope: str = "all"          # "all" or a layout id
    data_dir: str = ""
    sidebar_visible: bool = True
    show_original: bool = False

    @classmethod
    def load(cls) -> "AppSettings":
        store = QSettings(ORGANISATION, APPLICATION)
        defaults = cls()
        return cls(
            highlight_colour=str(store.value("highlight_colour", defaults.highlight_colour)),
            accent_colour=str(store.value("accent_colour", defaults.accent_colour)),
            dim_level=int(store.value("dim_level", defaults.dim_level)),
            default_scope=str(store.value("default_scope", defaults.default_scope)),
            data_dir=str(store.value("data_dir", "") or default_data_dir()),
            sidebar_visible=str(store.value("sidebar_visible", "true")).lower() in
            ("true", "1", "yes"),
            show_original=str(store.value("show_original", "false")).lower() in
            ("true", "1", "yes"),
        )

    def save(self) -> None:
        store = QSettings(ORGANISATION, APPLICATION)
        store.setValue("highlight_colour", self.highlight_colour)
        store.setValue("accent_colour", self.accent_colour)
        store.setValue("dim_level", self.dim_level)
        store.setValue("default_scope", self.default_scope)
        store.setValue("data_dir", self.data_dir)
        store.setValue("sidebar_visible", "true" if self.sidebar_visible else "false")
        store.setValue("show_original", "true" if self.show_original else "false")
        store.sync()

    def with_changes(self, **changes) -> "AppSettings":
        return replace(self, **changes)
