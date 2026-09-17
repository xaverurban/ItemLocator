"""Turn one photographed or scanned sheet into a :class:`Page`."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np

from . import structure, textparse
from .imaging import Straightened, straighten
from .models import BBox, Bay, Page, Product, Shelf
from .ocr import OcrEngine, TextLine

log = logging.getLogger(__name__)

MAX_LABEL_LINES = 6
LOW_CONFIDENCE = 0.72


@dataclass
class ParseOptions:
    header_band: float = 0.085          # fraction of page height treated as header
    footer_band: float = 0.085
    label_line_gap: float = 1.9         # multiples of line height inside one label
    label_x_slack: float = 0.55         # multiples of line height allowed sideways
    min_label_confidence: float = 0.35
    detect_white_labels: bool = True
    zoom_pass: bool = True              # re-read tiny labels and notch lines zoomed in
    zoom_factor: float = 3.0            # fallback when the text height is unknown
    zoom_target_text_height: float = 34.0   # pixels of x-height the OCR models like
    zoom_factor_limits: tuple[float, float] = (2.0, 8.0)
    max_zoom_crops: int = 80


# ------------------------------------------------------------------ helpers
def _x_overlap(a: BBox, b: BBox) -> float:
    return max(0.0, min(a.x2, b.x2) - max(a.x, b.x))


def _white_label_boxes(image: np.ndarray, min_area: int = 300) -> list[BBox]:
    """The white rectangles the codes and names are printed on."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    level = max(150, int(np.percentile(blurred, 70)))
    mask = (blurred >= level).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    height, width = gray.shape[:2]
    boxes: list[BBox] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < min_area or w > width * 0.45 or h > height * 0.35 or w < 12 or h < 12:
            continue
        if cv2.contourArea(contour) < 0.62 * w * h:      # not rectangular enough
            continue
        boxes.append(BBox(float(x), float(y), float(w), float(h)))
    return boxes


def _snap_to_label_box(bbox: BBox, boxes: Sequence[BBox]) -> Optional[BBox]:
    """Grow a text box out to the white label it sits on, when there is one.

    Only a box that hugs the text counts: pale product photos are also white-ish
    and snapping to one of those would highlight the wrong thing.
    """

    text_area = max(bbox.w * bbox.h, 1.0)
    best: Optional[BBox] = None
    best_area = float("inf")
    for box in boxes:
        if not (box.x - 6 <= bbox.x and box.y - 6 <= bbox.y and
                box.x2 + 6 >= bbox.x2 and box.y2 + 6 >= bbox.y2):
            continue
        area = box.w * box.h
        if area > text_area * 2.2 or box.h > bbox.h * 2.0 or box.w > bbox.w * 2.0:
            continue
        if area < best_area:
            best, best_area = box, area
    return best


def _group_labels(lines: list[TextLine], options: ParseOptions) -> list[dict]:
    """Cluster OCR lines into labels: a code, wrapped name lines, then Cases:N."""

    ordered = sorted(lines, key=lambda ln: (ln.bbox.y, ln.bbox.x))
    used: set[int] = set()
    labels: list[dict] = []

    for index, line in enumerate(ordered):
        if index in used:
            continue
        code = textparse.code_candidate(line.text)
        if code is None:
            continue

        members = [index]
        name_parts: list[str] = []
        cases: Optional[int] = None
        cases_confidence = 0.0
        anchor = line
        current = line
        for follow in range(index + 1, len(ordered)):
            if follow in used:
                continue
            candidate = ordered[follow]
            gap = candidate.bbox.y - current.bbox.y2
            line_height = max(current.bbox.h, candidate.bbox.h, 6.0)
            if gap > options.label_line_gap * line_height:
                break
            if candidate.bbox.y < current.bbox.y - line_height:
                continue
            overlap = _x_overlap(anchor.bbox, candidate.bbox)
            if overlap < min(anchor.bbox.w, candidate.bbox.w) * 0.35 and \
                    abs(candidate.bbox.x - anchor.bbox.x) > options.label_x_slack * line_height:
                continue
            if textparse.parse_notch(candidate.text) or textparse.is_noise(candidate.text):
                break
            if textparse.code_candidate(candidate.text) is not None:
                break                                   # the next label starts here
            found_cases = textparse.parse_cases(candidate.text)
            members.append(follow)
            current = candidate
            if found_cases is not None:
                cases = found_cases
                cases_confidence = candidate.confidence
                break
            name_parts.append(candidate.text)
            if len(members) >= MAX_LABEL_LINES:
                break

        used.update(members)
        member_lines = [ordered[i] for i in members]
        bbox = member_lines[0].bbox
        for member in member_lines[1:]:
            bbox = bbox.union(member.bbox)
        confidences = [m.confidence for m in member_lines]
        labels.append({
            "code": code,
            "code_confidence": line.confidence,
            "name": textparse.clean_name(name_parts),
            "cases": cases,
            "cases_confidence": cases_confidence,
            "bbox": bbox,
            "confidence": float(min(confidences)) if confidences else 0.0,
            "lines": member_lines,
        })
    return labels


def _shelf_bands(notch_lines: list[tuple[float, textparse.NotchInfo, TextLine]],
                 rules: list[float], top: float, bottom: float,
                 product_ys: list[float]) -> tuple[list[tuple[float, float]], bool]:
    """Y ranges for one bay's shelves, plus whether labels head their own band.

    Sheets put the notch line at the edge of the shelf row it describes.  Which
    edge is a printing convention, so we test both and keep the one that leaves
    no products stranded outside a shelf.
    """

    if not notch_lines:
        return [], True

    ys = [y for y, _, _ in notch_lines]

    def bands_heading() -> list[tuple[float, float]]:
        edges = [max(top, ys[0] - 4)] + [(a + b) / 2 for a, b in zip(ys, ys[1:])] + [bottom]
        return list(zip(edges, edges[1:]))

    def bands_trailing() -> list[tuple[float, float]]:
        edges = [top] + [(a + b) / 2 for a, b in zip(ys, ys[1:])] + [min(bottom, ys[-1] + 4)]
        return list(zip(edges, edges[1:]))

    def orphans(bands: list[tuple[float, float]]) -> int:
        if not bands:
            return len(product_ys)
        low, high = bands[0][0], bands[-1][1]
        return sum(1 for y in product_ys if y < low or y > high)

    heading, trailing = bands_heading(), bands_trailing()
    label_heads = orphans(heading) <= orphans(trailing)
    bands = heading if label_heads else trailing

    # Snap band edges onto printed rules when one is close by.
    snapped: list[float] = []
    edges = [bands[0][0]] + [band[1] for band in bands]
    for edge in edges:
        near = [rule for rule in rules if abs(rule - edge) < 40]
        snapped.append(min(near, key=lambda r: abs(r - edge)) if near else edge)
    snapped[0] = min(snapped[0], edges[0])
    snapped[-1] = max(snapped[-1], edges[-1])
    for i in range(1, len(snapped)):
        snapped[i] = max(snapped[i], snapped[i - 1] + 1)
    return list(zip(snapped, snapped[1:])), label_heads


def _dedupe_labels(labels: list[dict]) -> list[dict]:
    """Drop repeat reads of one label (tiled OCR plus the zoom pass can overlap)."""

    kept: list[dict] = []
    for label in sorted(labels, key=lambda item: (-float(item["confidence"]),
                                                  -len(item["name"]))):
        duplicate = False
        for other in kept:
            box, other_box = label["bbox"], other["bbox"]
            near = (abs(box.cx - other_box.cx) < max(box.w, other_box.w) * 1.2 and
                    abs(box.cy - other_box.cy) < max(box.h, other_box.h) * 1.2)
            inter_w = min(box.x2, other_box.x2) - max(box.x, other_box.x)
            inter_h = min(box.y2, other_box.y2) - max(box.y, other_box.y)
            overlapping = inter_w > 0 and inter_h > 0 and (
                inter_w * inter_h) > min(box.w * box.h, other_box.w * other_box.h) * 0.3
            if label["code"] == other["code"] and (near or overlapping):
                duplicate = True
                break
            if overlapping and (not label["name"] or not other["name"]):
                duplicate = True
                break
        if not duplicate:
            kept.append(label)
    kept.sort(key=lambda item: (item["bbox"].cy, item["bbox"].cx))
    return kept


def _read_zoomed(image: np.ndarray, box: BBox, engine: OcrEngine, factor: float,
                 pad: int = 6) -> list[TextLine]:
    """OCR one small region blown up, then map the results back onto the page."""

    height, width = image.shape[:2]
    x1 = int(max(0, box.x - pad))
    y1 = int(max(0, box.y - pad))
    x2 = int(min(width, box.x2 + pad))
    y2 = int(min(height, box.y2 + pad))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return []
    crop = image[y1:y2, x1:x2]
    zoomed = cv2.resize(crop, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    lines = engine.read(zoomed)
    for line in lines:
        line.bbox = BBox(line.bbox.x / factor + x1, line.bbox.y / factor + y1,
                         line.bbox.w / factor, line.bbox.h / factor)
        if line.quad:
            line.quad = [(x / factor + x1, y / factor + y1) for x, y in line.quad]
        line.meta["zoomed"] = True
    return lines


def _estimate_text_height(image: np.ndarray, box: BBox) -> Optional[float]:
    """Median height of the ink blobs inside a region - roughly the text size."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape[:2]
    x1, y1 = int(max(0, box.x)), int(max(0, box.y))
    x2, y2 = int(min(width, box.x2)), int(min(height, box.y2))
    if x2 - x1 < 6 or y2 - y1 < 6:
        return None
    patch = gray[y1:y2, x1:x2]
    ink = cv2.adaptiveThreshold(cv2.GaussianBlur(patch, (3, 3), 0), 255,
                                cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    heights = [stats[index, cv2.CC_STAT_HEIGHT] for index in range(1, count)
               if 2 <= stats[index, cv2.CC_STAT_HEIGHT] <= 60
               and 1 <= stats[index, cv2.CC_STAT_WIDTH] <= 60
               and stats[index, cv2.CC_STAT_AREA] >= 3]
    if len(heights) < 4:
        return None
    return float(np.median(heights))


def _zoom_factor_for(image: np.ndarray, box: BBox, options: ParseOptions) -> float:
    """Blow a region up until its text is about the size the OCR models expect."""

    text_height = _estimate_text_height(image, box)
    if not text_height or text_height <= 0:
        return options.zoom_factor
    low, high = options.zoom_factor_limits
    return float(np.clip(options.zoom_target_text_height / text_height, low, high))


def _unread_text_regions(image: np.ndarray, lines: list[TextLine],
                         max_regions: int = 80) -> list[BBox]:
    """Find clumps of print that the page-wide OCR pass did not cover.

    The smallest labels on these sheets are around 5pt.  The detector skips them
    at page scale, but the ink is still there, so look for text-shaped blobs
    outside every box OCR already returned and hand those back for a zoomed read.
    """

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape[:2]
    ink = cv2.adaptiveThreshold(cv2.GaussianBlur(gray, (3, 3), 0), 255,
                                cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 10)

    # Mask out everything already read, plus the printed rules.
    for line in lines:
        box = line.bbox
        cv2.rectangle(ink, (int(box.x - 4), int(box.y - 4)), (int(box.x2 + 4), int(box.y2 + 4)),
                      0, -1)
    long_h = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (max(30, width // 12), 1)))
    long_v = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, height // 12))))
    ink = cv2.subtract(ink, cv2.bitwise_or(long_h, long_v))

    # Glue characters into words, words into lines, lines into a label block.
    grouped = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 3)), iterations=1)
    grouped = cv2.morphologyEx(grouped, cv2.MORPH_CLOSE,
                               cv2.getStructuringElement(cv2.MORPH_RECT, (15, 11)))

    contours, _ = cv2.findContours(grouped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions: list[tuple[float, BBox]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < 18 or h < 14 or w > width * 0.4 or h > height * 0.25:
            continue
        patch = ink[y:y + h, x:x + w]
        density = float((patch > 0).mean())
        if not 0.04 <= density <= 0.65:
            continue
        regions.append((w * h * density, BBox(float(x), float(y), float(w), float(h))))
    regions.sort(key=lambda item: -item[0])
    return [box for _, box in regions[:max_regions]]


def _rescue_small_labels(image: np.ndarray, lines: list[TextLine], labels: list[dict],
                         engine: OcrEngine, options: ParseOptions) -> list[dict]:
    """Zoom in on unread print and try to read a label out of it."""

    known_codes = [(label["code"], label["bbox"]) for label in labels]
    claimed: list[BBox] = [label["bbox"] for label in labels]

    def overlaps(a: BBox, b: BBox) -> bool:
        inter_w = min(a.x2, b.x2) - max(a.x, b.x)
        inter_h = min(a.y2, b.y2) - max(a.y, b.y)
        if inter_w <= 0 or inter_h <= 0:
            return False
        return (inter_w * inter_h) > min(a.w * a.h, b.w * b.h) * 0.25

    def already_known(code: str, box: BBox) -> bool:
        return any(code == known and abs(known_box.cx - box.cx) < max(box.w, known_box.w) * 2.5
                   and abs(known_box.cy - box.cy) < max(box.h, known_box.h) * 2.5
                   for known, known_box in known_codes)

    median_area = float(np.median([label["bbox"].w * label["bbox"].h for label in labels])) \
        if labels else 0.0

    rescued: list[dict] = []
    for region in _unread_text_regions(image, lines, options.max_zoom_crops):
        if any(overlaps(region, other) for other in claimed):
            continue
        zoom_lines = _read_zoomed(image, region, engine,
                                  _zoom_factor_for(image, region, options))
        if not zoom_lines:
            continue
        before = len(rescued)
        for label in _group_labels(zoom_lines, options):
            if already_known(label["code"], label["bbox"]):
                continue
            if any(overlaps(label["bbox"], other) for other in claimed):
                continue
            # A bare number with no name and no "Cases:" line is usually part of
            # a product photo, not a label - do not invent products from it.
            if label["cases"] is None and len(label["name"]) < 3:
                continue
            label["rescued"] = True
            label["confidence"] = min(float(label["confidence"]), 0.85)
            rescued.append(label)
            claimed.append(label["bbox"])
            known_codes.append((label["code"], label["bbox"]))

        if len(rescued) == before and median_area:
            # Print we can see but cannot read: surface it instead of dropping it,
            # so the review screen can show an empty label to fill in.
            area = region.w * region.h
            if 0.3 * median_area <= area <= 2.5 * median_area and len(zoom_lines) >= 2:
                rescued.append({
                    "code": "", "code_confidence": 0.0, "name": "", "cases": None,
                    "cases_confidence": 0.0, "bbox": region, "confidence": 0.2,
                    "lines": zoom_lines, "unreadable": True,
                })
                claimed.append(region)
    return rescued


def _label_quality(label: dict) -> tuple[int, float]:
    """Rank a label read: complete labels first, then by OCR confidence."""
    completeness = (1 if label["cases"] is not None else 0) + (1 if label["name"] else 0)
    return completeness, float(label["confidence"])


def _verify_weak_labels(image: np.ndarray, labels: list[dict], engine: OcrEngine,
                        options: ParseOptions, threshold: float = 0.82) -> list[dict]:
    """Re-read doubtful labels zoomed in, and keep whichever read is better.

    Small labels often come back from the page-wide pass half-read, or with two
    neighbours merged into one; zooming in usually resolves both.
    """

    result: list[dict] = []
    for label in labels:
        weak = (float(label["confidence"]) < threshold or label["cases"] is None
                or not label["name"])
        if not weak or label.get("rescued"):
            result.append(label)
            continue
        box = label["bbox"]
        margin_x, margin_y = box.w * 0.45, box.h * 0.45
        region = BBox(box.x - margin_x, box.y - margin_y,
                      box.w + 2 * margin_x, box.h + 2 * margin_y)
        zoom_lines = _read_zoomed(image, region, engine,
                                  _zoom_factor_for(image, region, options), pad=2)
        replacements = [candidate for candidate in _group_labels(zoom_lines, options)
                        if region.x - 6 <= candidate["bbox"].cx <= region.x2 + 6
                        and region.y - 6 <= candidate["bbox"].cy <= region.y2 + 6]
        if not replacements:
            result.append(label)
            continue
        best_new = max(_label_quality(candidate) for candidate in replacements)
        if best_new > _label_quality(label) or len(replacements) > 1:
            for candidate in replacements:
                candidate["confidence"] = min(float(candidate["confidence"]), 0.9)
                candidate["rechecked"] = True
            result.extend(replacements)
        else:
            result.append(label)
    return result


def _refine_notches(image: np.ndarray, entries: list, engine: OcrEngine,
                    options: ParseOptions, bay_x_ranges: list[tuple[float, float]]) -> list:
    """Re-read notch lines whose depth or slope did not come through."""

    refined = []
    for y, info, line in entries:
        if info.complete:
            refined.append((y, info, line))
            continue
        right_edge = line.bbox.x2
        for x_start, x_end in bay_x_ranges:
            if x_start <= line.bbox.x <= x_end:
                right_edge = max(right_edge, min(x_end - 4, line.bbox.x + (x_end - x_start) * 0.7))
                break
        region = BBox.from_xyxy(line.bbox.x - 4, line.bbox.y - 4, right_edge, line.bbox.y2 + 4)
        best = info
        for zoom_line in _read_zoomed(image, region, engine,
                                      _zoom_factor_for(image, region, options), pad=3):
            candidate = textparse.parse_notch(zoom_line.text)
            if candidate is None or candidate.notch != info.notch:
                continue
            if (candidate.complete or
                    (candidate.depth_cm is not None and best.depth_cm is None) or
                    (candidate.slope is not None and best.slope is None)):
                best = candidate
        refined.append((y, best, line))
    return refined


# -------------------------------------------------------------------- parser
def parse_image(image: np.ndarray, ocr_engine: OcrEngine, source_file: str = "",
                source_page_index: int = 0, options: Optional[ParseOptions] = None,
                straightened: Optional[Straightened] = None) -> tuple[Page, Straightened]:
    """Parse one already-loaded page image."""

    options = options or ParseOptions()
    flat = straightened or straighten(image, ocr_engine=ocr_engine)
    page_image = flat.image
    height, width = page_image.shape[:2]

    page = Page(source_file=source_file, source_page_index=source_page_index,
                size=(width, height), transform=flat.transform.tolist(),
                warnings=list(flat.warnings))

    lines = ocr_engine.read(page_image)
    log.info("%s: %d OCR lines", os.path.basename(source_file or "page"), len(lines))

    # ---------------------------------------------------------- page furniture
    header_lines = [ln for ln in lines if ln.bbox.cy < height * options.header_band]
    footer_lines = [ln for ln in lines if ln.bbox.cy > height * (1 - options.footer_band)]
    if header_lines:
        page.header_text = _header_title(header_lines)
        page.layout_name, page.layout_size = textparse.parse_header(page.header_text)
    for line in footer_lines + header_lines:
        numbers = textparse.parse_page_number(line.text)
        if numbers:
            page.number, page.total_pages = numbers
            break
    for line in lines:
        text = line.text.strip()
        if textparse.is_marker(text) and text.upper() not in {"IE"}:
            if text.upper() not in page.tags:
                page.tags.append(text.upper())

    # --------------------------------------------------------------- content
    notch_entries: list[tuple[float, textparse.NotchInfo, TextLine]] = []
    content_lines: list[TextLine] = []
    furniture = {id(line) for line in header_lines + footer_lines}
    for line in lines:
        if id(line) in furniture or textparse.is_noise(line.text):
            continue
        info = textparse.parse_notch(line.text)
        if info is not None:
            notch_entries.append((line.bbox.cy, info, line))
            continue
        content_lines.append(line)
    notch_entries = _merge_notch_entries(notch_entries, height)

    labels = _group_labels(content_lines, options)
    white_boxes = _white_label_boxes(page_image) if options.detect_white_labels else []
    if options.zoom_pass:
        before = len(labels)
        labels = _verify_weak_labels(page_image, labels, ocr_engine, options)
        if len(labels) != before:
            log.info("zoom pass re-read weak labels: %d -> %d", before, len(labels))
        rescued = _rescue_small_labels(page_image, lines, labels, ocr_engine, options)
        if rescued:
            log.info("zoom pass recovered %d label(s)", len(rescued))
            labels.extend(rescued)
    labels = _dedupe_labels(labels)

    # ------------------------------------------------------------------ grid
    grid = structure.detect_grid(page_image)
    bay_x_ranges = structure.bay_ranges(grid, width)
    grid_top, grid_bottom = grid.bounds[1], grid.bounds[3]
    if grid_bottom - grid_top < height * 0.3:
        grid_top, grid_bottom = height * 0.1, height * 0.92
    if options.zoom_pass:
        notch_entries = _refine_notches(page_image, notch_entries, ocr_engine, options,
                                        bay_x_ranges)

    # ------------------------------------------------------- bays and shelves
    # Each notch line belongs to exactly one bay: the one its left edge sits in.
    notches_by_bay: dict[int, list] = {index: [] for index in range(1, len(bay_x_ranges) + 1)}
    for entry in notch_entries:
        anchor = entry[2].bbox.x + min(entry[2].bbox.w * 0.15, 20.0)
        bay_index = None
        for index, (x_start, x_end) in enumerate(bay_x_ranges, start=1):
            if x_start <= anchor <= x_end:
                bay_index = index
                break
        if bay_index is None:
            bay_index = min(range(1, len(bay_x_ranges) + 1),
                            key=lambda i: min(abs(bay_x_ranges[i - 1][0] - anchor),
                                              abs(bay_x_ranges[i - 1][1] - anchor)))
        notches_by_bay[bay_index].append(entry)

    bays: list[Bay] = []
    for bay_index, (x_start, x_end) in enumerate(bay_x_ranges, start=1):
        bay = Bay(index=bay_index, x_range=(x_start, x_end))
        own_notches = sorted(notches_by_bay[bay_index], key=lambda entry: entry[0])
        rules = structure.horizontal_rules_in(grid, x_start, x_end)
        product_ys = [label["bbox"].cy for label in labels
                      if x_start <= label["bbox"].cx <= x_end]

        if own_notches:
            bands, _ = _shelf_bands(own_notches, rules, grid_top, grid_bottom, product_ys)
            for shelf_index, ((band_top, band_bottom), entry) in enumerate(
                    zip(bands, own_notches), start=1):
                info = entry[1]
                bay.shelves.append(Shelf(
                    index_from_top=shelf_index, y_range=(band_top, band_bottom),
                    notch=info.notch, depth_cm=info.depth_cm, slope=info.slope,
                    notch_text=info.raw, confidence=entry[2].confidence,
                ))
        bays.append(bay)

    # Bays printed without their own notch line share the shelves of the bay to
    # their left - the sheets rely on the reader to carry them across.
    for position, bay in enumerate(bays):
        if bay.shelves:
            continue
        for previous in reversed(bays[:position]):
            if previous.shelves:
                bay.shelves = [Shelf(**{**s.to_dict(), "y_range": tuple(s.y_range),
                                        "inherited": True})
                               for s in previous.shelves]
                bay.shelves_inherited = True
                page.warnings.append(
                    f"Bay {bay.index} has no notch line of its own - it was given bay "
                    f"{previous.index}'s shelves. Please confirm on the review screen.")
                break

    # ------------------------------------------------------------- products
    products: list[Product] = []
    for label in labels:
        bbox: BBox = label["bbox"]
        bay = _bay_for(bays, bbox.cx)
        shelf = _shelf_for(bay, bbox.cy) if bay else None
        confidence = float(label["confidence"])
        tags: list[str] = []
        if bay is None or shelf is None:
            tags.append("unplaced")
            confidence = min(confidence, 0.5)
        snapped = _snap_to_label_box(bbox, white_boxes)
        if label.get("unreadable"):
            tags.append("unreadable")
            confidence = 0.2
        if label.get("rescued"):
            tags.append("small-print")
        product = Product(
            code=label["code"], name=label["name"], cases=label["cases"],
            bbox=snapped or bbox,
            bay=bay.index if bay else 0,
            shelf=shelf.index_from_top if shelf else 0,
            confidence=confidence, tags=tags,
        )
        if label["cases"] is None:
            product.tags.append("no-cases")
            product.confidence = min(product.confidence, 0.6)
        if not product.name:
            product.tags.append("no-name")
            product.confidence = min(product.confidence, 0.55)
        products.append(product)

    _assign_positions(products)
    _assign_image_boxes(products, bays)
    page.bays = bays
    page.products = products
    page.confidence = float(np.mean([p.confidence for p in products])) if products else 0.0

    unreadable = [p for p in products if "unreadable" in p.tags]
    if unreadable:
        page.warnings.append(
            f"{len(unreadable)} label(s) were found but could not be read - they are on the "
            f"page as empty entries for you to fill in.")
    low = [p for p in products if p.confidence < LOW_CONFIDENCE]
    if low:
        page.warnings.append(f"{len(low)} of {len(products)} products need checking.")
    if not products:
        page.warnings.append("No products were found on this page.")
    if not any(bay.shelves for bay in bays):
        page.warnings.append("No 'Notch:' lines were read on this page.")

    return page, flat


def _header_title(header_lines: list[TextLine]) -> str:
    """The layout title, rebuilt from the largest row of text in the header."""

    rows: list[list[TextLine]] = []
    for line in sorted(header_lines, key=lambda ln: ln.bbox.cy):
        for row in rows:
            reference = row[0]
            if abs(reference.bbox.cy - line.bbox.cy) < max(reference.bbox.h, line.bbox.h) * 0.8:
                row.append(line)
                break
        else:
            rows.append([line])
    if not rows:
        return ""
    best = max(rows, key=lambda row: (sum(ln.bbox.h for ln in row) / len(row)))
    best.sort(key=lambda ln: ln.bbox.x)
    return " ".join(line.text.strip() for line in best).strip()


def _merge_notch_entries(entries: list[tuple[float, textparse.NotchInfo, TextLine]],
                         page_height: int) -> list[tuple[float, textparse.NotchInfo, TextLine]]:
    """Overlapping OCR tiles can read one notch line twice - keep the best read."""

    tolerance = max(12.0, page_height * 0.012)
    merged: list[tuple[float, textparse.NotchInfo, TextLine]] = []
    for entry in sorted(entries, key=lambda item: (item[0], item[2].bbox.x)):
        y, info, line = entry
        replaced = False
        for index, (other_y, other_info, other_line) in enumerate(merged):
            same_row = abs(other_y - y) <= tolerance
            # Only fold reads of the *same* line: different bays carry their own
            # "Notch: 33" at the same height, and those are different shelves.
            gap = max(line.bbox.x - other_line.bbox.x2, other_line.bbox.x - line.bbox.x2, 0.0)
            same_line = (_x_overlap(line.bbox, other_line.bbox) >
                         min(line.bbox.w, other_line.bbox.w) * 0.3) or gap < 25
            if same_row and same_line:
                def rank(candidate: textparse.NotchInfo) -> tuple:
                    return (candidate.complete,
                            candidate.depth_cm is not None,
                            candidate.slope is not None,
                            len(candidate.raw))
                if rank(info) > rank(other_info):
                    merged[index] = entry
                replaced = True
                break
        if not replaced:
            merged.append(entry)
    merged.sort(key=lambda item: item[0])
    return merged


def _bay_for(bays: list[Bay], x: float) -> Optional[Bay]:
    for bay in bays:
        if bay.x_range[0] <= x <= bay.x_range[1]:
            return bay
    return min(bays, key=lambda b: min(abs(b.x_range[0] - x), abs(b.x_range[1] - x))) \
        if bays else None


def _shelf_for(bay: Bay, y: float) -> Optional[Shelf]:
    for shelf in bay.shelves:
        if shelf.y_range[0] <= y <= shelf.y_range[1]:
            return shelf
    if not bay.shelves:
        return None
    return min(bay.shelves, key=lambda s: min(abs(s.y_range[0] - y), abs(s.y_range[1] - y)))


def _assign_positions(products: list[Product]) -> None:
    groups: dict[tuple[int, int], list[Product]] = {}
    for product in products:
        groups.setdefault((product.bay, product.shelf), []).append(product)
    for group in groups.values():
        group.sort(key=lambda p: p.bbox.cx if p.bbox else 0.0)
        for position, product in enumerate(group, start=1):
            product.position_left = position
            product.position_right = len(group) - position + 1


def _assign_image_boxes(products: list[Product], bays: list[Bay]) -> None:
    """Widen each label box to the product's slice of its shelf, for highlighting."""

    groups: dict[tuple[int, int], list[Product]] = {}
    for product in products:
        groups.setdefault((product.bay, product.shelf), []).append(product)
    bay_by_index = {bay.index: bay for bay in bays}
    for (bay_index, shelf_index), group in groups.items():
        bay = bay_by_index.get(bay_index)
        shelf = None
        if bay:
            shelf = next((s for s in bay.shelves if s.index_from_top == shelf_index), None)
        group.sort(key=lambda p: p.bbox.cx if p.bbox else 0.0)
        for position, product in enumerate(group):
            if product.bbox is None:
                continue
            left_edge = bay.x_range[0] if bay else product.bbox.x
            right_edge = bay.x_range[1] if bay else product.bbox.x2
            if position > 0:
                previous = group[position - 1]
                left_edge = (previous.bbox.x2 + product.bbox.x) / 2
            if position < len(group) - 1:
                following = group[position + 1]
                right_edge = (product.bbox.x2 + following.bbox.x) / 2
            top = shelf.y_range[0] if shelf else product.bbox.y
            bottom = shelf.y_range[1] if shelf else product.bbox.y2
            product.image_bbox = BBox.from_xyxy(min(left_edge, product.bbox.x),
                                                min(top, product.bbox.y),
                                                max(right_edge, product.bbox.x2),
                                                max(bottom, product.bbox.y2))
