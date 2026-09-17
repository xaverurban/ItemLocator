"""Debug overlays: draw what the parser believes onto the straightened page."""

from __future__ import annotations

import cv2
import numpy as np

from .models import Page

COLOUR_BAY = (255, 170, 60)          # BGR
COLOUR_SHELF = (90, 200, 90)
COLOUR_PRODUCT = (40, 220, 255)
COLOUR_LOW = (60, 120, 255)
COLOUR_TEXT = (20, 20, 20)


def _put_label(canvas: np.ndarray, text: str, origin: tuple[int, int],
               colour: tuple[int, int, int], scale: float = 0.5) -> None:
    x, y = origin
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    cv2.rectangle(canvas, (x, y - th - 4), (x + tw + 6, y + 3), colour, -1)
    cv2.putText(canvas, text, (x + 3, y), cv2.FONT_HERSHEY_SIMPLEX, scale, COLOUR_TEXT, 1,
                cv2.LINE_AA)


def draw_overlay(image: np.ndarray, page: Page, low_confidence: float = 0.72) -> np.ndarray:
    """Return a copy of the page with bays, shelves and products drawn on."""

    canvas = image.copy()
    height, width = canvas.shape[:2]

    for bay in page.bays:
        x1, x2 = int(bay.x_range[0]), int(bay.x_range[1])
        cv2.rectangle(canvas, (x1, 0), (x2, height - 1), COLOUR_BAY, 3)
        tag = f"Bay {bay.index}" + (" (shared shelves)" if bay.shelves_inherited else "")
        _put_label(canvas, tag, (x1 + 8, 34), COLOUR_BAY, 0.7)
        for shelf in bay.shelves:
            y1, y2 = int(shelf.y_range[0]), int(shelf.y_range[1])
            cv2.rectangle(canvas, (x1 + 4, y1), (x2 - 4, y2), COLOUR_SHELF, 2)
            parts = [f"S{shelf.index_from_top}"]
            if shelf.notch is not None:
                parts.append(f"notch {shelf.notch}")
            if shelf.depth_cm is not None:
                parts.append(f"{shelf.depth_cm:g}cm")
            if shelf.slope is not None:
                parts.append(f"slope {shelf.slope:g}")
            _put_label(canvas, " ".join(parts), (x1 + 10, y1 + 26), COLOUR_SHELF, 0.55)

    for product in page.products:
        if product.bbox is None:
            continue
        colour = COLOUR_PRODUCT if product.confidence >= low_confidence else COLOUR_LOW
        box = product.bbox
        cv2.rectangle(canvas, (int(box.x), int(box.y)), (int(box.x2), int(box.y2)), colour, 2)
        caption = f"{product.code} b{product.bay} s{product.shelf} p{product.position_left}"
        _put_label(canvas, caption, (int(box.x), max(14, int(box.y) - 4)), colour, 0.45)

    banner = (f"{page.layout_name} {page.layout_size}  page {page.number}"
              f"{f' of {page.total_pages}' if page.total_pages else ''}  "
              f"{len(page.products)} products")
    _put_label(canvas, banner, (10, height - 14), (255, 255, 255), 0.8)
    return canvas
