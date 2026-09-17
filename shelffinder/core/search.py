"""Product code search.

Matching is deliberately simple and total: every product in every layout is held
in memory (a few thousand rows at most), so a keystroke is a linear scan and the
UI never waits on a query.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, Optional, Sequence

from .models import Layout, Page, Product
from .textparse import normalise_code

MIN_QUERY_DIGITS = 3
DEFAULT_LIMIT = 50
MAX_SUGGESTIONS = 8


class MatchKind(IntEnum):
    """Ordered worst to best so the enum value doubles as a rank."""

    NEAR_MISS = 0
    CONTAINS = 1
    SUFFIX = 2
    EXACT = 3


@dataclass(frozen=True)
class IndexEntry:
    product: Product
    page: Page
    layout: Layout


@dataclass(frozen=True)
class SearchHit:
    product: Product
    page: Page
    layout: Layout
    kind: MatchKind
    match_start: int = 0            # where the query sits inside the code,
    match_length: int = 0           # so the UI can embolden those digits
    suggested_code: Optional[str] = None     # set on near misses
    reason: str = ""

    @property
    def code(self) -> str:
        return self.product.code

    def highlight(self) -> tuple[str, str, str]:
        """Split the code into (before, matched, after) for display."""
        code = self.product.code
        if self.match_length <= 0:
            return code, "", ""
        start = max(0, self.match_start)
        end = start + self.match_length
        return code[:start], code[start:end], code[end:]


@dataclass
class SearchResult:
    query: str
    normalised: str
    hits: list[SearchHit] = field(default_factory=list)
    suggestions: list[SearchHit] = field(default_factory=list)
    too_short: bool = False
    truncated: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.hits

    @property
    def single(self) -> Optional[SearchHit]:
        """The one hit to jump straight to, if there is exactly one."""
        return self.hits[0] if len(self.hits) == 1 else None

    def message(self) -> str:
        if self.too_short:
            return f"Type at least {MIN_QUERY_DIGITS} digits."
        if self.hits:
            return f"{len(self.hits)} match{'es' if len(self.hits) != 1 else ''}."
        text = f"No product ending in {self.normalised}"
        if self.suggestions:
            codes = ", ".join(dict.fromkeys(hit.code for hit in self.suggestions))
            return f"{text}. Did you mean {codes}?"
        return f"{text}."


def _near_miss_variants(code: str) -> list[tuple[str, str]]:
    """Codes one OCR slip away from ``code``: a wrong digit, or two swapped."""

    variants: dict[str, str] = {}
    for index in range(len(code)):
        for digit in "0123456789":
            if digit != code[index]:
                variants.setdefault(code[:index] + digit + code[index + 1:],
                                    "one digit different")
    for index in range(len(code) - 1):
        if code[index] != code[index + 1]:
            swapped = code[:index] + code[index + 1] + code[index] + code[index + 2:]
            variants.setdefault(swapped, "two digits swapped")
    variants.pop(code, None)
    return list(variants.items())


class ProductIndex:
    """Everything searchable, kept in memory."""

    def __init__(self, layouts: Iterable[Layout] = ()) -> None:
        self._entries: list[IndexEntry] = []
        for layout in layouts:
            self.add_layout(layout)

    # -- building ---------------------------------------------------------
    def add_layout(self, layout: Layout) -> None:
        for page in layout.pages:
            for product in page.products:
                if product.code:
                    self._entries.append(IndexEntry(product, page, layout))

    def remove_layout(self, layout_id: str) -> None:
        self._entries = [entry for entry in self._entries if entry.layout.id != layout_id]

    def rebuild(self, layouts: Iterable[Layout]) -> None:
        self._entries = []
        for layout in layouts:
            self.add_layout(layout)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def layouts(self) -> list[Layout]:
        seen: dict[str, Layout] = {}
        for entry in self._entries:
            seen.setdefault(entry.layout.id, entry.layout)
        return list(seen.values())

    # -- searching --------------------------------------------------------
    def _scope(self, layout_ids: Optional[Sequence[str]]) -> list[IndexEntry]:
        if not layout_ids:
            return self._entries
        wanted = set(layout_ids)
        return [entry for entry in self._entries if entry.layout.id in wanted]

    @staticmethod
    def _sort_key(hit: SearchHit) -> tuple:
        product, page = hit.product, hit.page
        return (-int(hit.kind), len(product.code), hit.layout.title.lower(),
                page.number, product.bay, product.shelf, product.position_left,
                product.code)

    def search(self, query: str, layout_ids: Optional[Sequence[str]] = None,
               limit: int = DEFAULT_LIMIT, suggest: bool = True) -> SearchResult:
        digits = normalise_code(query)
        result = SearchResult(query=query, normalised=digits)
        if len(digits) < MIN_QUERY_DIGITS:
            result.too_short = True
            return result

        entries = self._scope(layout_ids)
        hits: list[SearchHit] = []
        for entry in entries:
            code = entry.product.code
            if code == digits:
                kind, start = MatchKind.EXACT, 0
            elif code.endswith(digits):
                kind, start = MatchKind.SUFFIX, len(code) - len(digits)
            else:
                start = code.find(digits)
                if start < 0:
                    continue
                kind = MatchKind.CONTAINS
            hits.append(SearchHit(entry.product, entry.page, entry.layout, kind,
                                  match_start=start, match_length=len(digits)))

        hits.sort(key=self._sort_key)
        result.truncated = len(hits) > limit
        result.hits = hits[:limit]

        if not hits and suggest:
            result.suggestions = self._suggest(digits, entries)
        return result

    def _suggest(self, digits: str, entries: list[IndexEntry]) -> list[SearchHit]:
        """Near misses, so an OCR slip in a code still finds the product."""

        reasons = dict(_near_miss_variants(digits))
        if not reasons:
            return []
        found: list[SearchHit] = []
        for entry in entries:
            code = entry.product.code
            for variant, reason in reasons.items():
                if code == variant:
                    start, kind = 0, MatchKind.NEAR_MISS
                elif code.endswith(variant):
                    start, kind = len(code) - len(variant), MatchKind.NEAR_MISS
                else:
                    start = code.find(variant)
                    if start < 0:
                        continue
                    kind = MatchKind.NEAR_MISS
                found.append(SearchHit(entry.product, entry.page, entry.layout, kind,
                                       match_start=start, match_length=len(variant),
                                       suggested_code=code, reason=reason))
                break
        found.sort(key=lambda hit: (hit.reason != "one digit different",
                                    len(hit.product.code), hit.product.code))
        return found[:MAX_SUGGESTIONS]

    # -- reverse lookup ---------------------------------------------------
    def product_at(self, page: Page, x: float, y: float) -> Optional[Product]:
        """Which product was clicked on the page image."""

        best: Optional[Product] = None
        best_area = float("inf")
        for product in page.products:
            for box in (product.bbox, product.image_bbox):
                if box is None:
                    continue
                if box.x <= x <= box.x2 and box.y <= y <= box.y2:
                    area = box.w * box.h
                    if area < best_area:
                        best, best_area = product, area
        return best

    def entry_for(self, product: Product) -> Optional[IndexEntry]:
        for entry in self._entries:
            if entry.product is product or entry.product.id == product.id:
                return entry
        return None
