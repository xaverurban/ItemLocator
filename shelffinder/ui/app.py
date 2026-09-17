"""Application entry point: ``python -m shelffinder`` or ShelfFinder.exe."""

from __future__ import annotations

import logging
import os
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from ..core.library import Library
from . import theme
from .main_window import MainWindow
from .settings import APPLICATION, ORGANISATION, AppSettings, default_data_dir

LOG_NAME = "shelffinder.log"

USAGE = """ShelfFinder - find where a product goes on a printed shelf layout.

  ShelfFinder                 open the app
  ShelfFinder --selftest      check this build works, then exit
  ShelfFinder --version       print the version
  ShelfFinder --help          show this message
"""


def build_application(argv: list[str] | None = None) -> QApplication:
    application = QApplication.instance()
    if application is None:
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


def _setup_logging(data_dir: str) -> str:
    """Log to a file next to the data, so a packaged build can be debugged."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, LOG_NAME)
    handlers: list[logging.Handler] = [logging.FileHandler(path, encoding="utf-8")]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return path


def _install_crash_handler(log_path: str) -> None:
    def report(kind, value, tb) -> None:
        logging.critical("unhandled error", exc_info=(kind, value, tb))
        text = "".join(traceback.format_exception(kind, value, tb))[-1800:]
        try:
            QMessageBox.critical(None, "ShelfFinder hit a problem",
                                 f"{value}\n\nThe details are in:\n{log_path}\n\n{text}")
        except Exception:                                  # noqa: BLE001 - last resort
            pass

    sys.excepthook = report


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    if "--help" in arguments or "-h" in arguments:
        print(USAGE)
        return 0
    if "--version" in arguments:
        from .. import __version__
        print(f"ShelfFinder {__version__}")
        return 0
    if "--selftest" in arguments:
        from ..selftest import run
        return run()

    settings = AppSettings.load()
    if not settings.data_dir:
        settings = settings.with_changes(data_dir=default_data_dir())
        settings.save()

    log_path = _setup_logging(settings.data_dir)
    logging.info("starting ShelfFinder, data folder %s", settings.data_dir)

    application = build_application(argv)
    _install_crash_handler(log_path)
    application.setStyleSheet(theme.stylesheet(
        theme.Palette(accent=settings.accent_colour, highlight=settings.highlight_colour)))

    library = Library(settings.data_dir)
    window = MainWindow(library, settings)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
