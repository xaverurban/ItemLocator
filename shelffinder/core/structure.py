"""Grid detection: the printed rules that split a sheet into bays and shelves."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class GridLines:
    """Printed rules found on a straightened page, in page pixels."""

    verticals: list[float] = field(default_factory=list)     # x of bay dividers
    horizontals: list[tuple[float, float, float]] = field(default_factory=list)
    # each horizontal is (y, x_start, x_end)
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)   # x1, y1, x2, y2
    found: bool = False


def _binarise(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 25, 12)
    return binary


def _cluster(values: list[float], tolerance: float) -> list[float]:
    """Merge nearby coordinates into one line each."""
    if not values:
        return []
    values = sorted(values)
    clusters: list[list[float]] = [[values[0]]]
    for value in values[1:]:
        if value - clusters[-1][-1] <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [float(np.mean(group)) for group in clusters]


def detect_grid(image: np.ndarray, min_vertical_fraction: float = 0.35,
                min_horizontal_fraction: float = 0.10) -> GridLines:
    """Find bay dividers (long vertical rules) and shelf rules (horizontal)."""

    height, width = image.shape[:2]
    binary = _binarise(image)

    v_length = max(25, int(height * min_vertical_fraction))
    h_length = max(25, int(width * min_horizontal_fraction))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_length))
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_length, 1))
    v_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)
    h_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
    v_mask = cv2.dilate(v_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)))
    h_mask = cv2.dilate(h_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)))

    grid = GridLines()

    # -- outer frame: the union of both masks bounds the product area ------
    combined = cv2.bitwise_or(v_mask, h_mask)
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        if w > width * 0.5 and h > height * 0.3:
            grid.bounds = (float(x), float(y), float(x + w), float(y + h))
            grid.found = True
    if not grid.found:
        grid.bounds = (0.0, 0.0, float(width), float(height))

    x1, y1, x2, y2 = grid.bounds

    # -- vertical rules ----------------------------------------------------
    v_candidates: list[float] = []
    contours, _ = cv2.findContours(v_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < v_length or w > width * 0.05:
            continue
        v_candidates.append(x + w / 2.0)
    grid.verticals = _cluster(v_candidates, tolerance=max(6.0, width * 0.008))

    # -- horizontal rules --------------------------------------------------
    h_segments: list[tuple[float, float, float]] = []
    contours, _ = cv2.findContours(h_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < h_length or h > height * 0.03:
            continue
        h_segments.append((y + h / 2.0, float(x), float(x + w)))
    # Faint rules break into pieces: join collinear segments across small gaps.
    h_segments.sort()
    merged: list[tuple[float, float, float]] = []
    tolerance = max(6.0, height * 0.006)
    gap_tolerance = width * 0.22
    for y, start, end in h_segments:
        joined = False
        for index, (prev_y, prev_start, prev_end) in enumerate(merged):
            if abs(prev_y - y) > tolerance:
                continue
            gap = max(start - prev_end, prev_start - end, 0.0)
            if gap <= gap_tolerance:
                merged[index] = ((prev_y + y) / 2.0, min(prev_start, start), max(prev_end, end))
                joined = True
                break
        if not joined:
            merged.append((y, start, end))
    merged.sort()
    grid.horizontals = merged

    log.debug("grid: %d verticals, %d horizontals, bounds=%s",
              len(grid.verticals), len(grid.horizontals), grid.bounds)
    return grid


def bay_ranges(grid: GridLines, page_width: int,
               min_bay_width_fraction: float = 0.08) -> list[tuple[float, float]]:
    """Turn vertical rules into left-to-right bay x-ranges."""

    x1, _, x2, _ = grid.bounds
    if x2 - x1 < page_width * 0.3:
        x1, x2 = 0.0, float(page_width)

    inner = [x for x in grid.verticals if x1 + 4 < x < x2 - 4]
    edges = [x1] + sorted(inner) + [x2]

    ranges: list[tuple[float, float]] = []
    minimum = page_width * min_bay_width_fraction
    for left, right in zip(edges, edges[1:]):
        if right - left < minimum and ranges:
            ranges[-1] = (ranges[-1][0], right)     # a stray rule: fold it in
        elif right - left >= minimum:
            ranges.append((left, right))
    if not ranges:
        ranges = [(x1, x2)]
    return ranges


def horizontal_rules_in(grid: GridLines, x_start: float, x_end: float,
                        coverage: float = 0.35) -> list[float]:
    """Y positions of the shelf rules that cross a given bay."""

    width = max(x_end - x_start, 1.0)
    result: list[float] = []
    for y, start, end in grid.horizontals:
        overlap = min(end, x_end) - max(start, x_start)
        if overlap / width >= coverage:
            result.append(y)
    return sorted(result)
