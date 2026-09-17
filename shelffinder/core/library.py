"""The app's data folder: importing sheets, storing them, searching them.

This is the layer a UI talks to. It owns the data folder, the database and the
search index, and it has no UI imports - a phone app could drive the same class.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

import cv2
import numpy as np

from .imaging import Straightened, iter_input_files, load_source_pages, straighten
from .locate import Location, locate
from .pack import PackSummary, export_pack, import_pack
from .models import Layout, Page, Product, group_pages_into_layouts
from .ocr import OcrEngine, RapidOcrEngine
from .parser import ParseOptions, parse_image
from .search import ProductIndex, SearchResult
from .store import ExistingLayout, ImportMode, LayoutStore

log = logging.getLogger(__name__)

IMAGES_DIR = "images"
DATABASE_NAME = "shelffinder.sqlite"


@dataclass
class ImportProgress:
    """Where the import has got to, for a progress bar and a status line."""

    file_index: int
    file_count: int
    file_name: str
    stage: str                       # "reading", "straightening", "reading text", "saving"
    page_number: Optional[int] = None
    message: str = ""

    @property
    def fraction(self) -> float:
        if self.file_count <= 0:
            return 0.0
        stages = ("reading", "straightening", "reading text", "saving", "done")
        within = stages.index(self.stage) / len(stages) if self.stage in stages else 0.0
        return min(1.0, (self.file_index + within) / self.file_count)


@dataclass
class ImportedPage:
    page: Page
    straightened: Straightened


@dataclass
class ImportReport:
    layouts: list[Layout] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)   # (file, reason)
    seconds: float = 0.0

    @property
    def product_count(self) -> int:
        return sum(len(page.products) for page in self.pages)

    def warnings(self) -> list[str]:
        out: list[str] = []
        for page in self.pages:
            for warning in page.warnings:
                out.append(f"{os.path.basename(page.source_file)}: {warning}")
        for layout in self.layouts:
            for number, duplicates in layout.duplicate_pages().items():
                names = ", ".join(os.path.basename(p.source_file) for p in duplicates)
                out.append(f"{layout.title}: page {number} was imported "
                           f"{len(duplicates)} times ({names}).")
        return out


@dataclass
class LayoutConflict:
    """A layout that is already in the library under the same name and size."""

    incoming: Layout
    existing: list[ExistingLayout]


class Library:
    """Everything the app knows, on disk and in memory."""

    def __init__(self, data_dir: str, ocr_engine: Optional[OcrEngine] = None,
                 parse_options: Optional[ParseOptions] = None) -> None:
        self.data_dir = os.path.abspath(data_dir)
        self.images_dir = os.path.join(self.data_dir, IMAGES_DIR)
        os.makedirs(self.images_dir, exist_ok=True)
        self.store = LayoutStore(os.path.join(self.data_dir, DATABASE_NAME))
        self.index = ProductIndex()
        self.parse_options = parse_options or ParseOptions()
        self._ocr_engine = ocr_engine
        self._layouts: list[Layout] = []
        self.reload()

    # -- lifecycle --------------------------------------------------------
    @property
    def ocr_engine(self) -> OcrEngine:
        """Built on first use: loading the OCR models takes a moment."""
        if self._ocr_engine is None:
            self._ocr_engine = RapidOcrEngine()
        return self._ocr_engine

    def close(self) -> None:
        self.store.close()

    def reload(self) -> None:
        self._layouts = self.store.load_all()
        self.index.rebuild(self._layouts)

    @property
    def layouts(self) -> list[Layout]:
        return list(self._layouts)

    def layout_of(self, page: Page) -> Optional[Layout]:
        for layout in self._layouts:
            if any(other.id == page.id for other in layout.pages):
                return layout
        return None

    # -- paths ------------------------------------------------------------
    def resolve(self, relative_path: str) -> str:
        if not relative_path:
            return ""
        if os.path.isabs(relative_path):
            return relative_path
        return os.path.join(self.data_dir, relative_path)

    def page_image_path(self, page: Page, original: bool = False) -> str:
        stored = page.original_image if original else page.straightened_image
        path = self.resolve(stored)
        if path and os.path.exists(path):
            return path
        # Fall back to the other one rather than showing nothing.
        other = self.resolve(page.straightened_image if original else page.original_image)
        return other if other and os.path.exists(other) else ""

    # -- importing --------------------------------------------------------
    def import_paths(self, paths: Sequence[str],
                     progress: Optional[Callable[[ImportProgress], None]] = None,
                     should_cancel: Optional[Callable[[], bool]] = None) -> ImportReport:
        """Parse sheets and copy their images into the data folder.

        Nothing is written to the database here - call :meth:`commit` once the
        user has decided what to do about layouts that already exist.
        """

        files = list(iter_input_files(list(paths)))
        report = ImportReport()
        started = time.time()

        def announce(index: int, name: str, stage: str, page_number=None, message="") -> None:
            if progress:
                progress(ImportProgress(index, len(files), name, stage, page_number, message))

        for file_index, path in enumerate(files):
            name = os.path.basename(path)
            if should_cancel and should_cancel():
                break
            try:
                announce(file_index, name, "reading")
                for source in load_source_pages(path):
                    if should_cancel and should_cancel():
                        break
                    announce(file_index, name, "straightening",
                             source.source_page_index + 1)
                    flat = straighten(source.image, ocr_engine=self.ocr_engine)
                    announce(file_index, name, "reading text", source.source_page_index + 1)
                    page, flat = parse_image(source.image, self.ocr_engine, source_file=path,
                                             source_page_index=source.source_page_index,
                                             options=self.parse_options, straightened=flat)
                    announce(file_index, name, "saving", page.number)
                    self._store_images(page, source.image, flat)
                    report.pages.append(page)
            except Exception as error:                      # noqa: BLE001 - reported to the user
                log.exception("import failed for %s", path)
                report.failures.append((path, str(error)))
            announce(file_index, name, "done", message=f"{len(report.pages)} page(s) so far")

        report.layouts = group_pages_into_layouts(report.pages)
        report.seconds = time.time() - started
        return report

    def _store_images(self, page: Page, original: np.ndarray, flat: Straightened) -> None:
        straight_name = f"{page.id}_straight.png"
        original_name = f"{page.id}_original.jpg"
        cv2.imwrite(os.path.join(self.images_dir, straight_name), flat.image)
        cv2.imwrite(os.path.join(self.images_dir, original_name), original,
                    [cv2.IMWRITE_JPEG_QUALITY, 88])
        page.straightened_image = os.path.join(IMAGES_DIR, straight_name)
        page.original_image = os.path.join(IMAGES_DIR, original_name)

    def adopt_images(self, page: Page, straightened: str, original: str = "") -> None:
        """Copy images produced elsewhere into the data folder and point the page at them.

        Used by the command line, which writes its debug output to its own
        folder: the library has to own a copy, or the page loses its picture the
        moment that folder is cleaned up.
        """

        for source, suffix, attribute in ((straightened, "straight", "straightened_image"),
                                          (original, "original", "original_image")):
            if not source or not os.path.exists(source):
                continue
            extension = os.path.splitext(source)[1].lower() or ".png"
            name = f"{page.id}_{suffix}{extension}"
            target = os.path.join(self.images_dir, name)
            if os.path.abspath(source) != os.path.abspath(target):
                shutil.copy2(source, target)
            setattr(page, attribute, os.path.join(IMAGES_DIR, name))

    def conflicts(self, report: ImportReport) -> list[LayoutConflict]:
        found: list[LayoutConflict] = []
        for layout in report.layouts:
            existing = self.store.find_matching(layout.name, layout.size)
            if existing:
                found.append(LayoutConflict(layout, existing))
        return found

    def commit(self, report: ImportReport,
               modes: Optional[dict[str, ImportMode]] = None,
               default_mode: ImportMode = ImportMode.KEEP_BOTH) -> list[str]:
        """Write imported layouts to the database. Returns the stored layout ids."""
        modes = modes or {}
        stored: list[str] = []
        for layout in report.layouts:
            stored.append(self.store.add_layout(layout, modes.get(layout.id, default_mode)))
        self.reload()
        return stored

    # -- editing ----------------------------------------------------------
    def save_page(self, page: Page) -> None:
        """Persist edits made on the review screen."""
        layout = self.layout_of(page)
        if layout is None:
            raise ValueError("that page does not belong to a stored layout")
        self.store.update_page(layout.id, page)
        self.reload()

    def delete_layout(self, layout_id: str) -> None:
        layout = self.store.get_layout(layout_id)
        if layout is not None:
            for page in layout.pages:
                for stored in (page.straightened_image, page.original_image):
                    path = self.resolve(stored)
                    if path and os.path.exists(path) and path.startswith(self.images_dir):
                        try:
                            os.remove(path)
                        except OSError:                     # noqa: PERF203 - best effort
                            log.warning("could not delete %s", path)
        self.store.delete_layout(layout_id)
        self.reload()

    # -- layout packs -----------------------------------------------------
    def export_pack(self, destination: str, layout_ids: Optional[Sequence[str]] = None,
                    include_originals: bool = False,
                    progress: Optional[Callable[[int, int, str], None]] = None) -> PackSummary:
        """Write layouts to a pack zip another machine - or the phone - can read."""
        chosen = [layout for layout in self._layouts
                  if not layout_ids or layout.id in set(layout_ids)]
        if not chosen:
            raise ValueError("there is nothing to export")
        return export_pack(chosen, destination, resolve=self.resolve,
                           include_originals=include_originals, progress=progress)

    def import_pack(self, path: str, mode: ImportMode = ImportMode.KEEP_BOTH) -> list[str]:
        """Read a pack and store its layouts, copying the images into the data folder."""
        layouts = import_pack(path, self.images_dir)
        stored: list[str] = []
        for layout in layouts:
            for page in layout.pages:
                for attribute in ("straightened_image", "original_image"):
                    value = getattr(page, attribute)
                    if value:
                        setattr(page, attribute,
                                os.path.join(IMAGES_DIR, os.path.basename(value)))
            stored.append(self.store.add_layout(layout, mode))
        self.reload()
        return stored

    # -- searching --------------------------------------------------------
    def search(self, query: str, layout_ids: Optional[Sequence[str]] = None,
               limit: int = 50) -> SearchResult:
        return self.index.search(query, layout_ids=layout_ids, limit=limit)

    def locate(self, product: Product, page: Page) -> Optional[Location]:
        layout = self.layout_of(page)
        return locate(product, page, layout) if layout else None

    def product_at(self, page: Page, x: float, y: float) -> Optional[Product]:
        return self.index.product_at(page, x, y)

    # -- housekeeping -----------------------------------------------------
    def stats(self) -> dict[str, int]:
        return {"layouts": len(self._layouts),
                "pages": sum(len(layout.pages) for layout in self._layouts),
                "products": self.store.count_products()}

    def copy_data_folder(self, destination: str) -> str:
        """Move the library to a new folder (used by the settings dialog)."""
        destination = os.path.abspath(destination)
        if destination == self.data_dir:
            return destination
        os.makedirs(destination, exist_ok=True)
        self.store.close()
        for name in os.listdir(self.data_dir):
            source = os.path.join(self.data_dir, name)
            target = os.path.join(destination, name)
            if os.path.isdir(source):
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
        self.data_dir = destination
        self.images_dir = os.path.join(destination, IMAGES_DIR)
        os.makedirs(self.images_dir, exist_ok=True)
        self.store = LayoutStore(os.path.join(destination, DATABASE_NAME))
        self.reload()
        return destination
