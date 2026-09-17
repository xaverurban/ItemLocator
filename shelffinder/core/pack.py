"""Layout packs: a zip of JSON plus page images.

A pack is how a processed layout moves between machines - desktop to desktop, or
desktop to the phone app - without redoing OCR. The format is deliberately
plain: one JSON document and a folder of images.

    pack.zip
      pack.json            schema, export date, and the layouts in full
      images/<page id>.jpg  the straightened page, downscaled for a phone
      images/<page id>_original.jpg   the photo it came from (optional)

Every page in ``pack.json`` names its images by their path inside the zip, so a
reader only needs a zip library and a JSON parser.
"""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional, Sequence

import cv2
import numpy as np

from .models import Layout, Page

PACK_SCHEMA_VERSION = 1
PACK_JSON = "pack.json"
PACK_IMAGES = "images"
DEFAULT_LONG_SIDE = 2200        # enough to read the smallest labels when zoomed
DEFAULT_QUALITY = 82


@dataclass
class PackSummary:
    path: str
    layouts: int
    pages: int
    products: int
    bytes: int

    def describe(self) -> str:
        return (f"{self.layouts} layout(s), {self.pages} page(s), {self.products} products, "
                f"{self.bytes / 1_000_000:.1f} MB")


def _resized_jpeg(image_path: str, long_side: int, quality: int) -> Optional[bytes]:
    image = cv2.imread(image_path)
    if image is None:
        return None
    height, width = image.shape[:2]
    scale = min(1.0, long_side / float(max(height, width)))
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ok else None


def export_pack(layouts: Sequence[Layout], destination: str,
                resolve: Callable[[str], str] = lambda path: path,
                include_originals: bool = False,
                long_side: int = DEFAULT_LONG_SIDE,
                quality: int = DEFAULT_QUALITY,
                progress: Optional[Callable[[int, int, str], None]] = None) -> PackSummary:
    """Write ``layouts`` and their page images to a pack zip.

    ``resolve`` turns a stored image path into a real path on disk; the default
    assumes the paths are already absolute.
    """

    pages = [page for layout in layouts for page in layout.pages]
    payload = {
        "schema_version": PACK_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "shelffinder",
        "layouts": [],
    }

    os.makedirs(os.path.dirname(os.path.abspath(destination)) or ".", exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, layout in enumerate(layouts):
            document = layout.to_dict()
            for page_index, page in enumerate(layout.pages):
                stored = document["pages"][page_index]
                if progress:
                    progress(sum(len(lay.pages) for lay in layouts[:index]) + page_index,
                             len(pages), f"page {page.number} of {layout.title}")

                name = f"{PACK_IMAGES}/{page.id}.jpg"
                data = _resized_jpeg(resolve(page.straightened_image), long_side, quality)
                if data:
                    archive.writestr(name, data)
                    stored["straightened_image"] = name
                else:
                    stored["straightened_image"] = ""

                if include_originals and page.original_image:
                    original_name = f"{PACK_IMAGES}/{page.id}_original.jpg"
                    original = _resized_jpeg(resolve(page.original_image), long_side, quality)
                    if original:
                        archive.writestr(original_name, original)
                        stored["original_image"] = original_name
                        continue
                stored["original_image"] = ""
            payload["layouts"].append(document)

        archive.writestr(PACK_JSON, json.dumps(payload, indent=2))

    return PackSummary(
        path=destination,
        layouts=len(layouts),
        pages=len(pages),
        products=sum(len(page.products) for page in pages),
        bytes=os.path.getsize(destination),
    )


def read_pack_manifest(path: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        with archive.open(PACK_JSON) as handle:
            payload = json.load(handle)
    version = int(payload.get("schema_version", 0))
    if version > PACK_SCHEMA_VERSION:
        raise ValueError(
            f"this pack was made by a newer version of ShelfFinder "
            f"(pack schema {version}, this build reads {PACK_SCHEMA_VERSION})")
    return payload


def import_pack(path: str, images_dir: str) -> list[Layout]:
    """Unpack a pack: extract its images into ``images_dir`` and return the layouts.

    The returned pages point at the extracted files, so they can be stored and
    opened exactly like freshly imported ones.
    """

    payload = read_pack_manifest(path)
    os.makedirs(images_dir, exist_ok=True)
    layouts = [Layout.from_dict(document) for document in payload.get("layouts", [])]

    with zipfile.ZipFile(path) as archive:
        members = set(archive.namelist())
        for layout in layouts:
            for page in layout.pages:
                for attribute in ("straightened_image", "original_image"):
                    inside = getattr(page, attribute)
                    if not inside or inside not in members:
                        setattr(page, attribute, "")
                        continue
                    target_name = os.path.basename(inside)
                    target = os.path.join(images_dir, target_name)
                    with archive.open(inside) as source, open(target, "wb") as handle:
                        handle.write(source.read())
                    setattr(page, attribute, target)
    return layouts
