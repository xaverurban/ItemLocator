"""Data model for parsed planogram sheets.

Plain dataclasses with JSON round-tripping.  No image objects are stored here -
images live on disk and are referenced by path - so a whole layout serialises to
a small JSON document that a phone app can consume directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Optional

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class BBox:
    """Axis-aligned box in straightened-page pixel coordinates."""

    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    def union(self, other: "BBox") -> "BBox":
        x1 = min(self.x, other.x)
        y1 = min(self.y, other.y)
        x2 = max(self.x2, other.x2)
        y2 = max(self.y2, other.y2)
        return BBox(x1, y1, x2 - x1, y2 - y1)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BBox":
        return cls(float(d["x"]), float(d["y"]), float(d["w"]), float(d["h"]))

    @classmethod
    def from_xyxy(cls, x1: float, y1: float, x2: float, y2: float) -> "BBox":
        return cls(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))


@dataclass
class Product:
    code: str
    name: str
    cases: Optional[int] = None
    bbox: Optional[BBox] = None            # the white label
    image_bbox: Optional[BBox] = None      # label plus the product photo above it
    bay: int = 0                           # 1-based, customer-flow order
    shelf: int = 0                         # 1-based from the top
    position_left: int = 0                 # 1-based from the left of its shelf
    position_right: int = 0                # 1-based from the right of its shelf
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
    manually_edited: bool = False
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bbox"] = self.bbox.to_dict() if self.bbox else None
        d["image_bbox"] = self.image_bbox.to_dict() if self.image_bbox else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Product":
        d = dict(d)
        d["bbox"] = BBox.from_dict(d["bbox"]) if d.get("bbox") else None
        d["image_bbox"] = BBox.from_dict(d["image_bbox"]) if d.get("image_bbox") else None
        d.setdefault("tags", [])
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Shelf:
    index_from_top: int                    # 1-based
    y_range: tuple[float, float] = (0.0, 0.0)
    notch: Optional[int] = None
    depth_cm: Optional[float] = None
    slope: Optional[float] = None
    notch_text: str = ""
    confidence: float = 1.0
    inherited: bool = False                # notch line copied from the bay to the left

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["y_range"] = list(self.y_range)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Shelf":
        d = dict(d)
        d["y_range"] = tuple(d.get("y_range") or (0.0, 0.0))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Bay:
    index: int                             # 1-based, customer-flow order
    x_range: tuple[float, float] = (0.0, 0.0)
    shelves: list[Shelf] = field(default_factory=list)
    shelves_inherited: bool = False        # no notch line of its own - needs review

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "x_range": list(self.x_range),
            "shelves_inherited": self.shelves_inherited,
            "shelves": [s.to_dict() for s in self.shelves],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Bay":
        return cls(
            index=int(d["index"]),
            x_range=tuple(d.get("x_range") or (0.0, 0.0)),
            shelves_inherited=bool(d.get("shelves_inherited", False)),
            shelves=[Shelf.from_dict(s) for s in d.get("shelves", [])],
        )


@dataclass
class Page:
    number: int = 1                        # page X
    total_pages: Optional[int] = None      # of Y
    source_file: str = ""                  # the file the page came from
    source_page_index: int = 0             # 0-based index inside a multi-page PDF
    original_image: str = ""               # path, relative to the data folder
    straightened_image: str = ""
    transform: Optional[list[list[float]]] = None   # 3x3 original -> straightened
    size: tuple[int, int] = (0, 0)         # straightened (w, h)
    bays: list[Bay] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    header_text: str = ""
    layout_name: str = ""
    layout_size: str = ""
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 1.0
    id: str = field(default_factory=_new_id)

    def shelf_of(self, product: Product) -> Optional[Shelf]:
        bay = self.bay_of(product)
        if bay is None:
            return None
        for shelf in bay.shelves:
            if shelf.index_from_top == product.shelf:
                return shelf
        return None

    def bay_of(self, product: Product) -> Optional[Bay]:
        for bay in self.bays:
            if bay.index == product.bay:
                return bay
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "total_pages": self.total_pages,
            "source_file": self.source_file,
            "source_page_index": self.source_page_index,
            "original_image": self.original_image,
            "straightened_image": self.straightened_image,
            "transform": self.transform,
            "size": list(self.size),
            "header_text": self.header_text,
            "layout_name": self.layout_name,
            "layout_size": self.layout_size,
            "tags": list(self.tags),
            "warnings": list(self.warnings),
            "confidence": self.confidence,
            "bays": [b.to_dict() for b in self.bays],
            "products": [p.to_dict() for p in self.products],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Page":
        page = cls(
            id=d.get("id") or _new_id(),
            number=int(d.get("number", 1)),
            total_pages=d.get("total_pages"),
            source_file=d.get("source_file", ""),
            source_page_index=int(d.get("source_page_index", 0)),
            original_image=d.get("original_image", ""),
            straightened_image=d.get("straightened_image", ""),
            transform=d.get("transform"),
            size=tuple(d.get("size") or (0, 0)),
            header_text=d.get("header_text", ""),
            layout_name=d.get("layout_name", ""),
            layout_size=d.get("layout_size", ""),
            tags=list(d.get("tags", [])),
            warnings=list(d.get("warnings", [])),
            confidence=float(d.get("confidence", 1.0)),
        )
        page.bays = [Bay.from_dict(b) for b in d.get("bays", [])]
        page.products = [Product.from_dict(p) for p in d.get("products", [])]
        return page


@dataclass
class Layout:
    name: str = ""
    size: str = ""
    imported_at: str = field(default_factory=_now)
    pages: list[Page] = field(default_factory=list)
    id: str = field(default_factory=_new_id)

    @property
    def title(self) -> str:
        return f"{self.name} {self.size}".strip()

    def iter_products(self) -> Iterator[tuple[Page, Product]]:
        for page in self.pages:
            for product in page.products:
                yield page, product

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "imported_at": self.imported_at,
            "pages": [p.to_dict() for p in self.pages],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Layout":
        layout = cls(
            id=d.get("id") or _new_id(),
            name=d.get("name", ""),
            size=d.get("size", ""),
            imported_at=d.get("imported_at") or _now(),
        )
        layout.pages = [Page.from_dict(p) for p in d.get("pages", [])]
        return layout


def group_pages_into_layouts(pages: Iterable[Page]) -> list[Layout]:
    """Group parsed pages by their header, then order them by page number."""

    def key_of(page: "Page") -> tuple[str, str]:
        # OCR drops spaces ("IEHousehold"), so compare on letters and digits only.
        squash = lambda text: "".join(c for c in text.lower() if c.isalnum())  # noqa: E731
        return squash(page.layout_name), squash(page.layout_size)

    buckets: dict[tuple[str, str], Layout] = {}
    for page in pages:
        key = key_of(page)
        layout = buckets.get(key)
        if layout is None:
            layout = Layout(name=page.layout_name, size=page.layout_size)
            buckets[key] = layout
        layout.pages.append(page)
        # Keep the most readable spelling of the name we have seen.
        if page.layout_name.count(" ") > layout.name.count(" "):
            layout.name = page.layout_name
    layouts = list(buckets.values())
    for layout in layouts:
        layout.pages.sort(key=lambda p: (p.number, p.source_file, p.source_page_index))
    layouts.sort(key=lambda lay: lay.title.lower())
    return layouts
