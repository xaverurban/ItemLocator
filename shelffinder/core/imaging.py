"""Loading, page detection, perspective correction and auto-rotation.

Everything here works on plain numpy BGR arrays so the module stays usable from
a CLI, a worker thread or a server.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Iterator, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS

A4_RATIO = 210.0 / 297.0          # portrait width / height
TARGET_LONG_SIDE = 3100           # straightened page long side, in pixels
MAX_UPSCALE = 1.25                # never invent detail that is not in the photo


@dataclass
class SourcePage:
    """One page's worth of pixels, straight off disk."""

    image: np.ndarray
    source_file: str
    source_page_index: int = 0


@dataclass
class Straightened:
    image: np.ndarray
    transform: np.ndarray                    # 3x3, original -> straightened
    quad: Optional[np.ndarray] = None        # detected page corners in the original
    rotation: int = 0                        # degrees applied after the warp
    page_detected: bool = True
    blur_score: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_original(self, points: np.ndarray) -> np.ndarray:
        """Map straightened-page points back onto the original photo."""
        inverse = np.linalg.inv(self.transform)
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, inverse).reshape(-1, 2)


# --------------------------------------------------------------------- loading
def _load_heif(path: str) -> np.ndarray:
    from PIL import Image
    import pillow_heif

    pillow_heif.register_heif_opener()
    with Image.open(path) as handle:
        return cv2.cvtColor(np.array(handle.convert("RGB")), cv2.COLOR_RGB2BGR)


def load_source_pages(path: str, pdf_dpi: int = 220) -> Iterator[SourcePage]:
    """Yield every page contained in ``path`` (a PDF can hold several)."""

    ext = os.path.splitext(path)[1].lower()
    if ext in PDF_EXTENSIONS:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(path)
        try:
            for index in range(len(document)):
                page = document[index]
                bitmap = page.render(scale=pdf_dpi / 72.0)
                array = bitmap.to_numpy()
                if array.ndim == 3 and array.shape[2] == 4:
                    array = cv2.cvtColor(array, cv2.COLOR_RGBA2BGR)
                elif array.ndim == 3:
                    array = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
                else:
                    array = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
                yield SourcePage(array, path, index)
        finally:
            document.close()
        return

    if ext in {".heic", ".heif"}:
        yield SourcePage(_load_heif(path), path, 0)
        return

    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"could not read image: {path}")
    yield SourcePage(image, path, 0)


def iter_input_files(paths: list[str]) -> Iterator[str]:
    """Expand folders and drop anything that is not a supported sheet."""
    for path in paths:
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                    yield os.path.join(path, name)
        elif os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS:
            yield path


# -------------------------------------------------------------- page detection
def _order_quad(points: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    total = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    return np.array([
        pts[np.argmin(total)],
        pts[np.argmin(diff)],
        pts[np.argmax(total)],
        pts[np.argmax(diff)],
    ], dtype=np.float32)


def _quad_area(quad: np.ndarray) -> float:
    return float(abs(cv2.contourArea(quad.astype(np.float32))))


def _rect_candidates(gray: np.ndarray, image_area: float) -> list[np.ndarray]:
    """Propose page quads from edges and from brightness, several settings each."""

    candidates: list[np.ndarray] = []
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    def add(contour) -> None:
        area = cv2.contourArea(contour)
        if area < image_area * 0.12:
            return
        peri = cv2.arcLength(contour, True)
        for eps in (0.02, 0.035, 0.05):
            approx = cv2.approxPolyDP(contour, eps * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                candidates.append(approx.reshape(4, 2).astype(np.float32))
                break
        candidates.append(cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32))

    # Edge-driven proposals.
    for low, high in ((30, 90), (50, 150), (75, 200)):
        edges = cv2.Canny(blurred, low, high)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            add(contour)

    # Brightness-driven proposals: paper is the big pale blob.
    otsu, _ = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    levels = {int(otsu), int(otsu) + 12, int(otsu) + 25,
              int(np.percentile(blurred, 65)), int(np.percentile(blurred, 80))}
    for level in sorted(level for level in levels if 40 < level < 250):
        mask = (blurred >= level).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for index in range(1, count):
            if stats[index, cv2.CC_STAT_AREA] < image_area * 0.12:
                continue
            component = (labels == index).astype(np.uint8)
            contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                add(contour)

    full = np.array([[0, 0], [gray.shape[1] - 1, 0],
                     [gray.shape[1] - 1, gray.shape[0] - 1], [0, gray.shape[0] - 1]],
                    dtype=np.float32)
    candidates.append(full)
    return candidates


def _edge_support(quad: np.ndarray, edge_map: np.ndarray, samples: int = 60) -> float:
    """Fraction of the quad's perimeter that sits on a real image edge.

    A genuine page boundary has gradient along all four sides; a box clipped by
    the frame, or one drawn through background clutter, does not.
    """

    height, width = edge_map.shape[:2]
    ordered = _order_quad(quad)
    hits = total = 0
    for index in range(4):
        start, end = ordered[index], ordered[(index + 1) % 4]
        for step in range(samples):
            t = (step + 0.5) / samples
            x = int(round(start[0] + (end[0] - start[0]) * t))
            y = int(round(start[1] + (end[1] - start[1]) * t))
            if x <= 1 or y <= 1 or x >= width - 2 or y >= height - 2:
                continue        # on the frame: a scan's page edge is not visible there
            total += 1
            if edge_map[y, x] > 0:
                hits += 1
    if total < samples:         # mostly frame - stay neutral instead of punishing it
        return 0.45
    return hits / total


def _score_quad(quad: np.ndarray, gray: np.ndarray, edge_map: np.ndarray) -> float:
    """How much does this quad look like a sheet of paper on a background?"""

    height, width = gray.shape[:2]
    image_area = float(height * width)
    area = _quad_area(quad)
    if area < image_area * 0.12 or area > image_area * 1.02:
        return -1.0

    ordered = _order_quad(quad)
    side_top = np.linalg.norm(ordered[1] - ordered[0])
    side_bottom = np.linalg.norm(ordered[2] - ordered[3])
    side_left = np.linalg.norm(ordered[3] - ordered[0])
    side_right = np.linalg.norm(ordered[2] - ordered[1])
    if min(side_top, side_bottom, side_left, side_right) < 20:
        return -1.0
    balance = min(side_top, side_bottom) / max(side_top, side_bottom)
    balance *= min(side_left, side_right) / max(side_left, side_right)
    if balance < 0.55:
        return -1.0

    mean_side_w = (side_top + side_bottom) / 2
    mean_side_h = (side_left + side_right) / 2
    ratio = max(mean_side_w, mean_side_h) / max(1e-6, min(mean_side_w, mean_side_h))
    aspect = float(np.exp(-abs(ratio - 1 / A4_RATIO) / 0.35))

    mask = np.zeros((height, width), np.uint8)
    cv2.fillConvexPoly(mask, ordered.astype(np.int32), 255)
    eroded = cv2.erode(mask, np.ones((9, 9), np.uint8), iterations=2)
    interior = gray[eroded > 0] if np.any(eroded > 0) else gray[mask > 0]
    inside = float(interior.mean()) if interior.size else 0.0
    outside_mask = cv2.bitwise_not(cv2.dilate(mask, np.ones((9, 9), np.uint8), iterations=2))
    outside_pixels = gray[outside_mask > 0]
    if outside_pixels.size < image_area * 0.02:
        contrast = 0.45                         # a scan where the page fills the frame
    else:
        contrast = float(np.clip((inside - outside_pixels.mean()) / 90.0, 0.0, 1.0))

    brightness = float(np.clip((inside - 110) / 110.0, 0.0, 1.0))
    # Paper is mostly paper-white with ink on it: most interior pixels are pale.
    pale = float((interior > max(150.0, inside * 0.92)).mean()) if interior.size else 0.0
    rect_area = cv2.contourArea(cv2.boxPoints(cv2.minAreaRect(ordered.astype(np.float32))))
    rectangularity = float(np.clip(area / max(rect_area, 1.0), 0.0, 1.0))
    coverage = float(np.clip(area / image_area, 0.0, 1.0))
    support = _edge_support(ordered, edge_map)

    return (2.4 * aspect + 1.6 * contrast + 1.0 * brightness + 1.6 * pale +
            1.2 * rectangularity + 0.4 * coverage + 0.6 * balance + 3.0 * support)


def detect_page_quad(image: np.ndarray, work_width: int = 1100) -> tuple[Optional[np.ndarray], bool]:
    """Find the sheet of paper. Returns (quad in original coords, detected)."""

    height, width = image.shape[:2]
    scale = min(work_width / float(max(width, height)), 1.0)
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    image_area = float(gray.shape[0] * gray.shape[1])
    edge_map = cv2.dilate(cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120),
                          np.ones((5, 5), np.uint8), iterations=1)

    best_quad: Optional[np.ndarray] = None
    best_score = float("-inf")
    for candidate in _rect_candidates(gray, image_area):
        score = _score_quad(candidate, gray, edge_map)
        if score > best_score:
            best_quad, best_score = candidate, score

    full_score = _score_quad(np.array([[0, 0], [gray.shape[1] - 1, 0],
                                       [gray.shape[1] - 1, gray.shape[0] - 1],
                                       [0, gray.shape[0] - 1]], dtype=np.float32), gray, edge_map)
    if best_quad is None:
        full = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
        return full, False

    if _quad_area(best_quad) < image_area * 0.985:
        detected = True
    else:
        # We ended up with the whole frame: fine for a scan or a PDF export, a
        # miss on a photo. Pale, low-clutter frames are scans.
        pale = float((gray > 150).mean())
        detected = bool(pale > 0.55 and best_score >= full_score - 1e-6)
    quad = _order_quad(best_quad) / scale
    quad[:, 0] = np.clip(quad[:, 0], 0, width - 1)
    quad[:, 1] = np.clip(quad[:, 1], 0, height - 1)
    return quad.astype(np.float32), bool(detected)


def _target_size(quad: np.ndarray) -> tuple[int, int]:
    top_left, top_right, bottom_right, bottom_left = quad
    width = (np.linalg.norm(top_right - top_left) + np.linalg.norm(bottom_right - bottom_left)) / 2
    height = (np.linalg.norm(bottom_left - top_left) + np.linalg.norm(bottom_right - top_right)) / 2
    if width <= 0 or height <= 0:
        raise ValueError("degenerate page quad")
    ratio = width / height
    # Snap to A4 when the measured shape is close - perspective makes the raw
    # measurement noisy and we know these are A4 sheets.
    for candidate in (A4_RATIO, 1 / A4_RATIO):
        if abs(ratio - candidate) / candidate < 0.14:
            ratio = candidate
            break
    measured_long = max(width, height)
    long_side = min(float(TARGET_LONG_SIDE), measured_long * MAX_UPSCALE)
    long_side = max(long_side, 1200.0)
    if ratio >= 1:
        out_w = int(round(long_side))
        out_h = int(round(long_side / ratio))
    else:
        out_h = int(round(long_side))
        out_w = int(round(long_side * ratio))
    return out_w, out_h


def warp_page(image: np.ndarray, quad: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    out_w, out_h = _target_size(quad)
    destination = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
                           dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(quad.astype(np.float32), destination)
    warped = cv2.warpPerspective(image, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
    return warped, matrix


# ------------------------------------------------------------------- rotation
_ROTATION_CODES = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}

_ORIENTATION_KEYWORDS = ("notch", "depth", "slope", "cases", "customer", "flow", "layout",
                         "lidl", "ambient", "chiller", "plinth", "contact")


def rotate_image(image: np.ndarray, degrees: int) -> np.ndarray:
    degrees %= 360
    if degrees == 0:
        return image
    return cv2.rotate(image, _ROTATION_CODES[degrees])


def rotation_matrix(degrees: int, width: int, height: int) -> np.ndarray:
    """Homography for rotating a (width x height) image clockwise by ``degrees``."""
    degrees %= 360
    if degrees == 0:
        return np.eye(3, dtype=np.float64)
    if degrees == 90:
        return np.array([[0, -1, height - 1], [1, 0, 0], [0, 0, 1]], dtype=np.float64)
    if degrees == 180:
        return np.array([[-1, 0, width - 1], [0, -1, height - 1], [0, 0, 1]], dtype=np.float64)
    return np.array([[0, 1, 0], [-1, 0, width - 1], [0, 0, 1]], dtype=np.float64)


def text_direction_score(lines) -> float:
    """How strongly the text reads left-to-right rather than top-to-bottom.

    The OCR models happily read a line of text that is lying on its side - they
    rotate each detected box before recognising it - so what the text *says*
    cannot tell us which way up the page is. The shape of the boxes can: on an
    upright page every line is wider than it is tall.
    """

    if not lines:
        return 0.0
    wide = weight = 0.0
    for line in lines:
        confidence = float(line.confidence)
        weight += confidence
        if line.bbox.w > line.bbox.h:
            wide += confidence
    if weight <= 0:
        return 0.0
    fraction = wide / weight
    # More readable lines is also better evidence, with sharply diminishing returns.
    return fraction * float(np.log1p(len(lines)))


def upside_down_score(lines, page_height: float) -> float:
    """Positive when the page looks like it is the wrong way up.

    Nothing here relies on the words being unreadable upside down, because they
    are not. It relies on where things sit on a planogram: notch numbers count
    down the page, the title is at the top, the flow arrow and page number are
    at the bottom.
    """

    from . import textparse

    score = 0.0

    # Notch numbers run from the highest shelf at the top to the lowest at the
    # bottom, so notch value should fall as y rises.
    notches: list[tuple[float, int]] = []
    for line in lines:
        info = textparse.parse_notch(line.text)
        if info is not None and info.notch is not None:
            notches.append((line.bbox.cy, info.notch))
    if len(notches) >= 3:
        agree = disagree = 0
        for i in range(len(notches)):
            for j in range(i + 1, len(notches)):
                (y_a, notch_a), (y_b, notch_b) = notches[i], notches[j]
                if abs(y_a - y_b) < page_height * 0.02 or notch_a == notch_b:
                    continue
                lower_on_page = y_a > y_b
                smaller_notch = notch_a < notch_b
                if lower_on_page == smaller_notch:
                    agree += 1
                else:
                    disagree += 1
        if agree + disagree >= 3:
            score += 6.0 * (disagree - agree) / (agree + disagree)

    for line in lines:
        text = " ".join(line.text.lower().split())
        near_top = line.bbox.cy < page_height * 0.18
        near_bottom = line.bbox.cy > page_height * 0.82
        if textparse.parse_page_number(line.text) and len(text) <= 12:
            score += 1.5 if near_top else (-1.5 if near_bottom else 0.0)
        if "customer" in text and "flow" in text:
            score += 2.0 if near_top else (-2.0 if near_bottom else 0.0)
        if "layoutmanagement" in text.replace(" ", "") or "lidl.ie" in text:
            score += 1.5 if near_bottom else (-1.5 if near_top else 0.0)
        if "visible notch" in text or "plinth" in text:
            score += 1.5 if near_top else (-1.5 if near_bottom else 0.0)

    return score


def reading_quality(lines) -> float:
    """How much of this reads like a planogram rather than like noise."""

    from . import textparse

    score = 0.0
    for line in lines:
        confidence = float(line.confidence)
        if textparse.parse_notch(line.text) is not None:
            score += 3.0 * confidence
        elif textparse.parse_cases(line.text) is not None:
            score += 1.5 * confidence
        elif textparse.code_candidate(line.text) is not None:
            score += 1.0 * confidence
    return score


def detect_rotation(image: np.ndarray, ocr_engine, probe_long_side: int = 1400,
                    return_detail: bool = False):
    """Return the clockwise rotation (0/90/180/270) that makes the page upright.

    Two questions, answered separately: which way the lines of text run, and
    whether the page is the right way up along that axis.
    """

    height, width = image.shape[:2]
    scale = min(1.0, probe_long_side / float(max(width, height)))
    probe = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    readings = {angle: ocr_engine.read(rotate_image(probe, angle)) for angle in (0, 90)}
    scores = {angle: text_direction_score(lines) for angle, lines in readings.items()}
    axis = max(scores, key=lambda angle: scores[angle])

    lines = readings[axis]
    page_height = float(rotate_image(probe, axis).shape[0])
    flip = upside_down_score(lines, page_height)

    quality = None
    if abs(flip) < 1.0:
        # Nothing on the page said which way up it is. Read it the other way up
        # and keep whichever reads better: recognition is a little sharper when
        # the text is not upside down, even though it is still legible.
        upside_down = ocr_engine.read(rotate_image(probe, (axis + 180) % 360))
        quality = (reading_quality(lines), reading_quality(upside_down))
        if quality[1] > quality[0] * 1.05:
            flip = 1.0

    rotation = (axis + (180 if flip > 0 else 0)) % 360

    detail = {
        "axis": axis,
        "direction_scores": scores,
        "flip_score": flip,
        "quality": quality,
        "lines": {angle: len(found) for angle, found in readings.items()},
    }
    log.info("rotation %d deg (axis %d, direction %s, flip %.1f)", rotation, axis,
             {angle: round(value, 2) for angle, value in scores.items()}, flip)
    return (rotation, detail) if return_detail else rotation


def blur_score(image: np.ndarray) -> float:
    """Variance of Laplacian - low means soft or out of focus."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    small = cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


def straighten(image: np.ndarray, ocr_engine=None, blur_threshold: float = 60.0) -> Straightened:
    """Detect the sheet, flatten it and turn it upright."""

    warnings: list[str] = []
    quad, detected = detect_page_quad(image)
    if not detected:
        warnings.append("Page edges not found - using the whole image. "
                        "Re-shoot with the full sheet in frame for better results.")
    warped, matrix = warp_page(image, quad)

    rotation = 0
    if ocr_engine is not None:
        rotation, detail = detect_rotation(warped, ocr_engine, return_detail=True)
        direction = sorted(detail["direction_scores"].values(), reverse=True)
        if direction[0] <= 0.5:
            warnings.append("Hardly any text could be read on this page - it may be "
                            "blurry or cropped. Check it before relying on it.")
        elif len(direction) > 1 and direction[1] > direction[0] * 0.85:
            warnings.append("Which way round this page goes was a close call - "
                            "check the page looks right.")
        elif abs(detail["flip_score"]) < 1.0:
            warnings.append("Whether this page is upside down was a close call - "
                            "check the page looks right.")
    elif warped.shape[1] > warped.shape[0]:
        rotation = 90
    if rotation:
        warped = rotate_image(warped, rotation)
        matrix = rotation_matrix(rotation, *(_pre_rotation_size(warped, rotation))) @ matrix

    sharpness = blur_score(warped)
    if sharpness < blur_threshold:
        warnings.append(f"Page looks blurry (sharpness {sharpness:.0f}). "
                        "Consider re-shooting this page.")

    return Straightened(image=warped, transform=matrix, quad=quad, rotation=rotation,
                        page_detected=detected, blur_score=sharpness, warnings=warnings)


def map_points(transform, points, inverse: bool = False) -> list[tuple[float, float]]:
    """Move points between the original photo and the straightened page.

    ``transform`` is the 3x3 matrix on :class:`Straightened` (original ->
    straightened); pass ``inverse=True`` to go the other way, which is what the
    viewer needs to draw a highlight on top of the original photo.
    """

    matrix = np.asarray(transform, dtype=np.float64).reshape(3, 3)
    if inverse:
        matrix = np.linalg.inv(matrix)
    array = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
    mapped = cv2.perspectiveTransform(array, matrix.astype(np.float64)).reshape(-1, 2)
    return [(float(x), float(y)) for x, y in mapped]


def map_box(transform, box, inverse: bool = False) -> list[tuple[float, float]]:
    """Map a box's four corners, which perspective turns into a quadrilateral."""
    x1, y1, x2, y2 = box
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    return map_points(transform, corners, inverse=inverse)


def _pre_rotation_size(rotated: np.ndarray, degrees: int) -> tuple[int, int]:
    """Width/height the image had *before* the rotation was applied."""
    height, width = rotated.shape[:2]
    if degrees % 180 == 0:
        return width, height
    return height, width
