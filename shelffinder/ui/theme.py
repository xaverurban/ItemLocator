"""Dark theme: a few tokens and the stylesheet built from them."""

from __future__ import annotations

from dataclasses import dataclass

BACKGROUND = "#0F1115"
PANEL = "#171A21"
PANEL_RAISED = "#1E222B"
BORDER = "#2A2F3A"
TEXT = "#E6E9EF"
TEXT_DIM = "#8B93A7"
TEXT_FAINT = "#5C6479"
AMBER = "#F2B441"
RED = "#E5484D"
GREEN = "#46C98B"

DEFAULT_ACCENT = "#5B8CFF"      # one UI accent colour
DEFAULT_HIGHLIGHT = "#FFD400"   # pops on a greyscale printout

RADIUS = 8
FONT_STACK = '"Inter", "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif'


@dataclass(frozen=True)
class Palette:
    accent: str = DEFAULT_ACCENT
    highlight: str = DEFAULT_HIGHLIGHT


def stylesheet(palette: Palette) -> str:
    accent = palette.accent
    return f"""
    * {{ font-family: {FONT_STACK}; }}
    QWidget {{ background: {BACKGROUND}; color: {TEXT}; font-size: 14px; }}
    QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}

    QFrame#Panel, QWidget#Panel {{
        background: {PANEL}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
    }}
    QLabel#Heading {{ font-size: 13px; color: {TEXT_DIM}; font-weight: 600;
                      letter-spacing: 0.6px; }}
    QLabel#Hint {{ color: {TEXT_FAINT}; }}
    QLabel#EmptyState {{ color: {TEXT_FAINT}; font-size: 20px; }}

    QLineEdit#SearchBox {{
        background: {PANEL_RAISED}; border: 1px solid {BORDER};
        border-radius: {RADIUS}px; padding: 10px 14px; font-size: 22px;
        font-weight: 600; letter-spacing: 2px; selection-background-color: {accent};
    }}
    QLineEdit#SearchBox:focus {{ border: 1px solid {accent}; }}

    QPushButton {{
        background: {PANEL_RAISED}; border: 1px solid {BORDER};
        border-radius: {RADIUS}px; padding: 7px 14px; color: {TEXT};
    }}
    QPushButton:hover {{ background: {BORDER}; }}
    QPushButton:pressed {{ background: {PANEL}; }}
    QPushButton#Primary {{ background: {accent}; border: 1px solid {accent}; color: #0B1020;
                           font-weight: 600; }}
    QPushButton#Primary:hover {{ background: {accent}; }}
    QPushButton:checked {{ border: 1px solid {accent}; color: {accent}; }}
    QPushButton:disabled {{ color: {TEXT_FAINT}; }}

    QComboBox {{
        background: {PANEL_RAISED}; border: 1px solid {BORDER};
        border-radius: {RADIUS}px; padding: 6px 10px; min-height: 22px;
    }}
    QComboBox:focus {{ border: 1px solid {accent}; }}
    QComboBox QAbstractItemView {{
        background: {PANEL_RAISED}; border: 1px solid {BORDER};
        selection-background-color: {accent}; selection-color: #0B1020; outline: none;
    }}

    QTreeWidget, QListWidget {{
        background: {PANEL}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
        outline: none; padding: 4px;
    }}
    QTreeWidget::item, QListWidget::item {{ padding: 6px 4px; border-radius: 6px; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {accent}; color: #0B1020;
    }}
    QTreeWidget::item:hover, QListWidget::item:hover {{ background: {PANEL_RAISED}; }}

    QListWidget#Results {{ background: {PANEL_RAISED}; border: 1px solid {accent}; }}
    QListWidget#Thumbnails {{ background: {PANEL}; border: none; }}

    QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; width: 10px;
        height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: {BORDER}; border-radius: 5px; min-height: 30px;
        min-width: 30px; }}
    QScrollBar::handle:hover {{ background: {TEXT_FAINT}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QStatusBar {{ background: {PANEL}; color: {TEXT_DIM}; border-top: 1px solid {BORDER}; }}
    QStatusBar::item {{ border: none; }}
    QProgressBar {{ background: {PANEL_RAISED}; border: 1px solid {BORDER};
        border-radius: 6px; height: 8px; text-align: center; color: {TEXT_DIM}; }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 6px; }}

    QToolTip {{ background: {PANEL_RAISED}; color: {TEXT}; border: 1px solid {BORDER};
        padding: 6px; border-radius: 6px; }}
    QDialog {{ background: {BACKGROUND}; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
        border: 1px solid {BORDER}; background: {PANEL_RAISED}; }}
    QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}
    QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {accent}; width: 14px; height: 14px;
        margin: -6px 0; border-radius: 7px; }}
    QSplitter::handle {{ background: {BACKGROUND}; }}
    QSplitter::handle:hover {{ background: {BORDER}; }}
    """
