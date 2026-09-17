"""Application entry point: ``python -m shelffinder``."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ..core.library import Library
from . import theme
from .main_window import MainWindow
from .settings import APPLICATION, ORGANISATION, AppSettings, default_data_dir


def build_application(argv: list[str] | None = None) -> QApplication:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    application = QApplication(argv if argv is not None else sys.argv)
    application.setOrganizationName(ORGANISATION)
    application.setApplicationName(APPLICATION)
    application.setApplicationDisplayName("ShelfFinder")
    for family in ("Inter", "Segoe UI", "Noto Sans", "DejaVu Sans"):
        font = QFont(family)
        if font.exactMatch() or family == "DejaVu Sans":
            font.setPointSize(10)
            application.setFont(font)
            break
    return application


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    application = build_application(argv)
    settings = AppSettings.load()
    if not settings.data_dir:
        settings = settings.with_changes(data_dir=default_data_dir())
        settings.save()

    application.setStyleSheet(theme.stylesheet(
        theme.Palette(accent=settings.accent_colour, highlight=settings.highlight_colour)))
    library = Library(settings.data_dir)
    window = MainWindow(library, settings)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
