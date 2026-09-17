"""Corrections to a parsed page, and the bookkeeping that follows them.

Moving a box, dragging a bay line or renaming a product all have knock-on
effects: which bay a product is in, which shelf, its position along that shelf,
and the area the viewer lights up. Everything here keeps those in step, so a UI
only has to say what changed.

No UI imports: the desktop review screen and the phone both use this.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .models import BBox, Bay, Page, Product, Shelf

EDITED_CONFIDENCE = 1.0


# ----------------------------------------------------------------- placement
def bay_for(bays: list[Bay], x: float) -> Optional[Bay]:
    for bay in bays:
        if bay.x_range[0] <= x <= bay.x_range[1]:
            return bay
    if not bays:
        return None
    return min(bays, key=lambda bay: min(abs(bay.x_range[0] - x), abs(bay.x_range[1] - x)))


def shelf_for(bay: Bay, y: float) -> Optional[Shelf]:
    for shelf in bay.shelves:
        if shelf.y_range[0] <= y <= shelf.y_range[1]:
            return shelf
    if not bay.shelves:
        return None
    return min(bay.shelves,
               key=lambda shelf: min(abs(shelf.y_range[0] - y), abs(shelf.y_range[1] - y)))


def assign_positions(products: list[Product]) -> None:
    """Number products along each shelf, from the left and from the right."""
    groups: dict[tuple[int, int], list[Product]] = {}
    for product in products:
        groups.setdefault((product.bay, product.shelf), []).append(product)
    for group in groups.values():
        group.sort(key=lambda product: product.bbox.cx if product.bbox else 0.0)
        for position, product in enumerate(group, start=1):
            product.position_left = position
            product.position_right = len(group) - position + 1


def assign_image_boxes(products: list[Product], bays: list[Bay]) -> None:
    """Widen each label box to the product's slice of its shelf, for tapping."""

    groups: dict[tuple[int, int], list[Product]] = {}
    for product in products:
        groups.setdefault((product.bay, product.shelf), []).append(product)
    bay_by_index = {bay.index: bay for bay in bays}
    for (bay_index, shelf_index), group in groups.items():
        bay = bay_by_index.get(bay_index)
        shelf = None
        if bay:
            shelf = next((s for s in bay.shelves if s.index_from_top == shelf_index), None)
        group.sort(key=lambda product: product.bbox.cx if product.bbox else 0.0)
        for position, product in enumerate(group):
            if product.bbox is None:
                continue
            left_edge = bay.x_range[0] if bay else product.bbox.x
            right_edge = bay.x_range[1] if bay else product.bbox.x2
            if position > 0:
                left_edge = (group[position - 1].bbox.x2 + product.bbox.x) / 2
            if position < len(group) - 1:
                right_edge = (product.bbox.x2 + group[position + 1].bbox.x) / 2
            top = shelf.y_range[0] if shelf else product.bbox.y
            bottom = shelf.y_range[1] if shelf else product.bbox.y2
            product.image_bbox = BBox.from_xyxy(min(left_edge, product.bbox.x),
                                                min(top, product.bbox.y),
                                                max(right_edge, product.bbox.x2),
                                                max(bottom, product.bbox.y2))


def replace_products(page: Page, products: Iterable[Product]) -> None:
    page.products = list(products)
    reassign(page)


def reassign(page: Page) -> None:
    """Put every product back in the bay and on the shelf its box now sits in."""

    for product in page.products:
        if product.bbox is None:
            continue
        bay = bay_for(page.bays, product.bbox.cx)
        product.bay = bay.index if bay else 0
        shelf = shelf_for(bay, product.bbox.cy) if bay else None
        product.shelf = shelf.index_from_top if shelf else 0
    assign_positions(page.products)
    assign_image_boxes(page.products, page.bays)


# ------------------------------------------------------------------ products
def mark_edited(product: Product) -> Product:
    product.manually_edited = True
    product.confidence = EDITED_CONFIDENCE
    for tag in ("unreadable", "no-name", "no-cases", "unplaced"):
        if tag in product.tags:
            product.tags.remove(tag)
    return product


def update_product(page: Page, product: Product, *, code: Optional[str] = None,
                   name: Optional[str] = None, cases: Optional[int] = None,
                   bbox: Optional[BBox] = None) -> Product:
    """Apply a correction and put the product back where it now belongs."""

    if code is not None:
        product.code = "".join(character for character in code if character.isdigit())
    if name is not None:
        product.name = name.strip()
    if cases is not None:
        product.cases = cases
    if bbox is not None:
        product.bbox = bbox
    mark_edited(product)
    reassign(page)
    return product


def add_product(page: Page, bbox: BBox, code: str = "", name: str = "",
                cases: Optional[int] = None) -> Product:
    product = Product(code="".join(c for c in code if c.isdigit()), name=name.strip(),
                      cases=cases, bbox=bbox, tags=["added-by-hand"])
    mark_edited(product)
    page.products.append(product)
    reassign(page)
    return product


def delete_product(page: Page, product: Product) -> bool:
    before = len(page.products)
    page.products = [other for other in page.products if other.id != product.id]
    if len(page.products) == before:
        return False
    reassign(page)
    return True


# ---------------------------------------------------------------- structure
def set_bay_edges(page: Page, edges: list[float]) -> None:
    """Redraw the bay dividers. Shelves follow the bay they were drawn for."""

    edges = sorted(set(round(edge, 2) for edge in edges))
    if len(edges) < 2:
        raise ValueError("a page needs at least two bay edges")

    old_bays = page.bays
    new_bays: list[Bay] = []
    for index, (left, right) in enumerate(zip(edges, edges[1:]), start=1):
        centre = (left + right) / 2
        source = bay_for(old_bays, centre) if old_bays else None
        shelves = [Shelf.from_dict(shelf.to_dict()) for shelf in source.shelves] \
            if source else []
        new_bays.append(Bay(index=index, x_range=(left, right), shelves=shelves,
                            shelves_inherited=source.shelves_inherited if source else False))
    page.bays = new_bays
    reassign(page)


def set_shelf_edges(page: Page, bay_index: int, edges: list[float]) -> None:
    """Redraw one bay's shelf bands, keeping each band's notch details."""

    bay = next((bay for bay in page.bays if bay.index == bay_index), None)
    if bay is None:
        raise ValueError(f"there is no bay {bay_index}")
    edges = sorted(set(round(edge, 2) for edge in edges))
    if len(edges) < 2:
        raise ValueError("a bay needs at least two shelf edges")

    previous = bay.shelves
    shelves: list[Shelf] = []
    for index, (top, bottom) in enumerate(zip(edges, edges[1:]), start=1):
        centre = (top + bottom) / 2
        source = shelf_for(bay, centre) if previous else None
        shelves.append(Shelf(
            index_from_top=index, y_range=(top, bottom),
            notch=source.notch if source else None,
            depth_cm=source.depth_cm if source else None,
            slope=source.slope if source else None,
            notch_text=source.notch_text if source else "",
            confidence=EDITED_CONFIDENCE,
            inherited=False,
        ))
    bay.shelves = shelves
    bay.shelves_inherited = False
    reassign(page)


def update_shelf(page: Page, bay_index: int, shelf_index: int, *,
                 notch: Optional[int] = None, depth_cm: Optional[float] = None,
                 slope: Optional[float] = None) -> Shelf:
    bay = next((bay for bay in page.bays if bay.index == bay_index), None)
    if bay is None:
        raise ValueError(f"there is no bay {bay_index}")
    shelf = next((s for s in bay.shelves if s.index_from_top == shelf_index), None)
    if shelf is None:
        raise ValueError(f"bay {bay_index} has no shelf {shelf_index}")
    if notch is not None:
        shelf.notch = notch
    if depth_cm is not None:
        shelf.depth_cm = depth_cm
    if slope is not None:
        shelf.slope = slope
    shelf.confidence = EDITED_CONFIDENCE
    shelf.inherited = False
    bay.shelves_inherited = False
    return shelf


# -------------------------------------------------------------------- review
@dataclass(frozen=True)
class ReviewSummary:
    total: int
    needs_checking: int
    unreadable: int
    missing_name: int
    missing_cases: int
    duplicate_codes: list[str]
    bays_sharing_shelves: list[int]
    shelves_without_notch: int

    @property
    def is_clean(self) -> bool:
        return (self.needs_checking == 0 and not self.bays_sharing_shelves
                and self.shelves_without_notch == 0)

    def describe(self) -> str:
        if self.total == 0:
            return "Nothing was read from this page."
        parts = [f"{self.total} products"]
        if self.needs_checking:
            parts.append(f"{self.needs_checking} to check")
        if self.bays_sharing_shelves:
            bays = ", ".join(str(index) for index in self.bays_sharing_shelves)
            parts.append(f"bay {bays} sharing shelves")
        if self.shelves_without_notch:
            parts.append(f"{self.shelves_without_notch} shelves with no notch read")
        return " · ".join(parts)


def needs_checking(product: Product, threshold: float = 0.72) -> bool:
    if product.manually_edited:
        return False
    return (product.confidence < threshold or not product.code or not product.name
            or product.cases is None or "unreadable" in product.tags
            or "unplaced" in product.tags)


def review_summary(page: Page, threshold: float = 0.72) -> ReviewSummary:
    """What a reviewer should look at on this page."""

    seen: dict[str, int] = {}
    for product in page.products:
        if product.code:
            seen[product.code] = seen.get(product.code, 0) + 1

    return ReviewSummary(
        total=len(page.products),
        needs_checking=sum(1 for p in page.products if needs_checking(p, threshold)),
        unreadable=sum(1 for p in page.products if "unreadable" in p.tags),
        missing_name=sum(1 for p in page.products if not p.name),
        missing_cases=sum(1 for p in page.products if p.cases is None),
        duplicate_codes=sorted(code for code, count in seen.items() if count > 1),
        bays_sharing_shelves=[bay.index for bay in page.bays if bay.shelves_inherited],
        shelves_without_notch=sum(1 for bay in page.bays for shelf in bay.shelves
                                  if shelf.notch is None),
    )
