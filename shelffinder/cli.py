"""Command line front end for the ShelfFinder parser.

    python -m shelffinder.cli parse samples/*.jpg --out out/

Writes, per page: the straightened image, a debug overlay and the parsed JSON,
plus a layouts.json grouping pages that belong to the same layout.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import time

import cv2

from .core import render
from .core.imaging import iter_input_files, load_source_pages
from .core.models import Layout, group_pages_into_layouts
from .core.ocr import RapidOcrEngine
from .core.parser import ParseOptions, parse_image

log = logging.getLogger("shelffinder")


def _expand(paths: list[str]) -> list[str]:
    expanded: list[str] = []
    for path in paths:
        matches = glob.glob(path)
        expanded.extend(matches if matches else [path])
    return list(iter_input_files(expanded))


def cmd_parse(args: argparse.Namespace) -> int:
    files = _expand(args.inputs)
    if not files:
        print("No input files found.", file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)
    engine = RapidOcrEngine(tile_size=args.tile_size)
    options = ParseOptions()

    pages = []
    for path in files:
        for source in load_source_pages(path, pdf_dpi=args.pdf_dpi):
            started = time.time()
            base = os.path.splitext(os.path.basename(path))[0]
            if source.source_page_index:
                base = f"{base}_p{source.source_page_index + 1}"
            page, flat = parse_image(source.image, engine, source_file=path,
                                     source_page_index=source.source_page_index,
                                     options=options)
            straight_path = os.path.join(args.out, f"{base}_straight.png")
            overlay_path = os.path.join(args.out, f"{base}_overlay.png")
            json_path = os.path.join(args.out, f"{base}.json")
            cv2.imwrite(straight_path, flat.image)
            cv2.imwrite(overlay_path, render.draw_overlay(flat.image, page))
            page.straightened_image = straight_path
            page.original_image = path
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(page.to_dict(), handle, indent=2)
            pages.append(page)

            print(f"{base}: {len(page.products)} products, {len(page.bays)} bays, "
                  f"page {page.number}"
                  f"{f' of {page.total_pages}' if page.total_pages else ''}, "
                  f"layout '{f'{page.layout_name} {page.layout_size}'.strip()}', "
                  f"{time.time() - started:.1f}s")
            for warning in page.warnings:
                print(f"    ! {warning}")

    layouts = group_pages_into_layouts(pages)
    layouts_path = os.path.join(args.out, "layouts.json")
    with open(layouts_path, "w", encoding="utf-8") as handle:
        json.dump([layout.to_dict() for layout in layouts], handle, indent=2)
    print(f"\n{len(layouts)} layout(s) -> {layouts_path}")
    for layout in layouts:
        print(f"  {layout.title}: {len(layout.pages)} page(s), "
              f"{sum(len(p.products) for p in layout.pages)} products")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shelffinder", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    parse_cmd = sub.add_parser("parse", help="parse sheets into JSON plus debug images")
    parse_cmd.add_argument("inputs", nargs="+", help="image/PDF files, globs or folders")
    parse_cmd.add_argument("--out", default="out", help="output folder (default: out)")
    parse_cmd.add_argument("--tile-size", type=int, default=1400, help="OCR tile size")
    parse_cmd.add_argument("--pdf-dpi", type=int, default=220, help="render DPI for PDFs")
    parse_cmd.add_argument("-v", "--verbose", action="store_true")
    parse_cmd.set_defaults(func=cmd_parse)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
