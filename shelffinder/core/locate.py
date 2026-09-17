"""Turn a search hit into the numbers a worker needs on the shop floor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Bay, Layout, Page, Product, Shelf


@dataclass(frozen=True)
class Neighbour:
    code: str
    name: str
    same_bay: bool

    def describe(self) -> str:
        label = f"{self.code} {self.name}".strip()
        return label if self.same_bay else f"{label} (next bay)"


@dataclass
class Location:
    """Everything the result card shows for one product."""

    product: Product
    page: Page
    layout: Layout
    bay: Optional[Bay]
    shelf: Optional[Shelf]
    bay_index: int                     # 1-based in customer-flow order
    bay_count: int
    shelf_from_top: int
    shelf_from_bottom: int
    position_left: int
    position_right: int
    position_count: int
    neighbour_left: Optional[Neighbour] = None
    neighbour_right: Optional[Neighbour] = None

    # -- convenience for the UI -------------------------------------------
    @property
    def code(self) -> str:
        return self.product.code

    @property
    def name(self) -> str:
        return self.product.name

    @property
    def cases(self) -> Optional[int]:
        return self.product.cases

    @property
    def needs_review(self) -> bool:
        return (self.product.confidence < 0.72 or not self.product.name
                or "unreadable" in self.product.tags
                or (self.bay is not None and self.bay.shelves_inherited))

    def page_label(self) -> str:
        title = self.layout.title or "Unknown layout"
        if self.page.total_pages:
            return f"{title}, page {self.page.number} of {self.page.total_pages}"
        return f"{title}, page {self.page.number}"

    def bay_label(self) -> str:
        return f"Bay {self.bay_index} of {self.bay_count}"

    def shelf_label(self) -> str:
        parts = [f"Shelf {self.shelf_from_top} from top"]
        if self.shelf_from_bottom:
            parts.append(f"{self.shelf_from_bottom} from bottom")
        return ", ".join(parts)

    def notch_label(self) -> str:
        if self.shelf is None or self.shelf.notch is None:
            return "Notch unknown"
        parts = [f"Notch {self.shelf.notch}"]
        if self.shelf.depth_cm is not None:
            parts.append(f"depth {self.shelf.depth_cm:g}cm")
        if self.shelf.slope is not None:
            parts.append(f"slope {self.shelf.slope:g}")
        return ", ".join(parts)

    def position_label(self) -> str:
        return (f"Position {self.position_left} from left, "
                f"{self.position_right} from right of {self.position_count}")

    def summary_lines(self) -> list[str]:
        lines = [f"{self.code}  {self.name}".strip(), self.page_label(), self.bay_label(),
                 f"{self.shelf_label()} ({self.notch_label()})", self.position_label()]
        if self.cases is not None:
            lines.append(f"Cases: {self.cases}")
        neighbours = []
        if self.neighbour_left:
            neighbours.append(f"left: {self.neighbour_left.describe()}")
        if self.neighbour_right:
            neighbours.append(f"right: {self.neighbour_right.describe()}")
        if neighbours:
            lines.append("Neighbours - " + "; ".join(neighbours))
        return lines


def bay_in_flow_order(page: Page, bay_index: int) -> int:
    """Bays are numbered along the customer flow, which is usually left to right."""
    if not page.customer_flow_reversed:
        return bay_index
    return max(1, len(page.bays) - bay_index + 1)


def shelf_row_products(page: Page, product: Product) -> list[Product]:
    """Every product on the same physical shelf run, across bay lines, left to right.

    Bays can have different shelf counts, so the run is defined by what the
    shelf's height band overlaps rather than by the shelf number.
    """

    shelf = page.shelf_of(product)
    if shelf is None or shelf.y_range[1] <= shelf.y_range[0]:
        same_shelf = [p for p in page.products if p.shelf == product.shelf]
        return sorted(same_shelf, key=lambda p: p.bbox.cx if p.bbox else 0.0)

    top, bottom = shelf.y_range
    height = bottom - top
    row: list[Product] = []
    for candidate in page.products:
        if candidate.bbox is None:
            continue
        other = page.shelf_of(candidate)
        if other is not None and other.y_range[1] > other.y_range[0]:
            # Two shelves are the same run when their height bands line up, which
            # is what lets a neighbour in the next bay count even though the bays
            # number their shelves independently.
            overlap = min(bottom, other.y_range[1]) - max(top, other.y_range[0])
            shorter = min(height, other.y_range[1] - other.y_range[0])
            if overlap <= 0 or overlap < shorter * 0.5:
                continue
        elif not top <= candidate.bbox.cy <= bottom:
            continue
        row.append(candidate)
    if product not in row:
        row.append(product)
    return sorted(row, key=lambda p: p.bbox.cx if p.bbox else 0.0)


def neighbours(page: Page, product: Product) -> tuple[Optional[Neighbour], Optional[Neighbour]]:
    row = shelf_row_products(page, product)
    try:
        index = row.index(product)
    except ValueError:
        return None, None

    def make(other: Product) -> Neighbour:
        return Neighbour(code=other.code, name=other.name, same_bay=other.bay == product.bay)

    left = make(row[index - 1]) if index > 0 else None
    right = make(row[index + 1]) if index + 1 < len(row) else None
    if page.customer_flow_reversed:
        left, right = right, left
    return left, right


def locate(product: Product, page: Page, layout: Layout) -> Location:
    bay = page.bay_of(product)
    shelf = page.shelf_of(product)
    shelf_count = len(bay.shelves) if bay and bay.shelves else 0
    shelf_from_bottom = (shelf_count - product.shelf + 1) if shelf_count and product.shelf else 0
    position_count = max(product.position_left + product.position_right - 1, 0)
    left, right = neighbours(page, product)
    return Location(
        product=product, page=page, layout=layout, bay=bay, shelf=shelf,
        bay_index=bay_in_flow_order(page, product.bay) if product.bay else 0,
        bay_count=len(page.bays),
        shelf_from_top=product.shelf,
        shelf_from_bottom=shelf_from_bottom,
        position_left=product.position_left,
        position_right=product.position_right,
        position_count=position_count,
        neighbour_left=left, neighbour_right=right,
    )


def locate_hit(hit) -> Location:
    """Convenience wrapper for a :class:`shelffinder.core.search.SearchHit`."""
    return locate(hit.product, hit.page, hit.layout)
