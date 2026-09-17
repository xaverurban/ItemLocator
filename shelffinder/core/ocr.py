"""OCR abstraction.

The rest of the code only ever sees :class:`TextLine`, so the engine can be
swapped (RapidOCR today, a cloud vision API or a phone-native OCR later) without
touching the parser.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence

import numpy as np

from .models import BBox

log = logging.getLogger(__name__)


@dataclass
class TextLine:
    text: str
    bbox: BBox
    confidence: float = 1.0
    quad: Optional[list[tuple[float, float]]] = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def height(self) -> float:
        return self.bbox.h


class OcrEngine(Protocol):
    def read(self, image: np.ndarray) -> list[TextLine]:
        ...


def _quad_to_bbox(quad: Sequence[Sequence[float]]) -> BBox:
    xs = [float(p[0]) for p in quad]
    ys = [float(p[1]) for p in quad]
    return BBox.from_xyxy(min(xs), min(ys), max(xs), max(ys))


def _iou(a: BBox, b: BBox) -> float:
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x2, b.x2), min(a.y2, b.y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    return inter / (a.w * a.h + b.w * b.h - inter)


def deduplicate(lines: list[TextLine], iou_threshold: float = 0.45) -> list[TextLine]:
    """Drop overlapping duplicates produced by tiled OCR, keeping the best read."""

    kept: list[TextLine] = []
    for line in sorted(lines, key=lambda ln: (-ln.confidence, -ln.bbox.w)):
        if any(_iou(line.bbox, other.bbox) > iou_threshold for other in kept):
            continue
        kept.append(line)
    kept.sort(key=lambda ln: (ln.bbox.cy, ln.bbox.x))
    return kept


class RapidOcrEngine:
    """Offline OCR via RapidOCR (PaddleOCR ONNX models).

    Large pages are read in overlapping tiles: the detector downscales its input,
    which loses the smallest labels on a full A4 page at 300 dpi.
    """

    def __init__(self, tile_size: int = 1400, overlap: float = 0.16,
                 min_confidence: float = 0.3, **engine_kwargs: Any) -> None:
        # The detector downscales anything longer than det_limit_side_len, which
        # is what loses the smallest labels - keep it at least the tile size.
        engine_kwargs.setdefault("det_limit_side_len", float(tile_size + 64))
        engine_kwargs.setdefault("det_limit_type", "max")
        self.tile_size = tile_size
        self.overlap = overlap
        self.min_confidence = min_confidence
        self._engine_kwargs = engine_kwargs
        self._engine = None

    # -- engine -----------------------------------------------------------
    @property
    def engine(self):
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise RuntimeError(
                    "RapidOCR is not installed. Run: pip install rapidocr-onnxruntime"
                ) from exc
            self._engine = RapidOCR(**self._engine_kwargs)
        return self._engine

    def _read_raw(self, image: np.ndarray) -> list[TextLine]:
        result, _ = self.engine(image)
        lines: list[TextLine] = []
        for item in result or []:
            quad, text, score = item[0], item[1], float(item[2])
            if score < self.min_confidence or not str(text).strip():
                continue
            lines.append(TextLine(text=str(text), bbox=_quad_to_bbox(quad),
                                  confidence=score,
                                  quad=[(float(p[0]), float(p[1])) for p in quad]))
        return lines

    # -- public -----------------------------------------------------------
    def read(self, image: np.ndarray) -> list[TextLine]:
        height, width = image.shape[:2]
        if max(height, width) <= self.tile_size:
            return deduplicate(self._read_raw(image))

        step = int(self.tile_size * (1 - self.overlap))
        lines: list[TextLine] = []
        for top in range(0, max(1, height - int(self.tile_size * self.overlap)), step):
            for left in range(0, max(1, width - int(self.tile_size * self.overlap)), step):
                bottom = min(height, top + self.tile_size)
                right = min(width, left + self.tile_size)
                tile = image[top:bottom, left:right]
                if tile.size == 0:
                    continue
                for line in self._read_raw(tile):
                    line.bbox = BBox(line.bbox.x + left, line.bbox.y + top,
                                     line.bbox.w, line.bbox.h)
                    if line.quad:
                        line.quad = [(x + left, y + top) for x, y in line.quad]
                    lines.append(line)
        return deduplicate(lines)


class NullOcrEngine:
    """Returns nothing - used by tests that only exercise geometry."""

    def read(self, image: np.ndarray) -> list[TextLine]:  # noqa: ARG002
        return []


def default_engine(**kwargs: Any) -> OcrEngine:
    return RapidOcrEngine(**kwargs)
