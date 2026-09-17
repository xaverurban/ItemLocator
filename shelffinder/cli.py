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
from .core.locate import locate_hit
from .core.models import Layout, group_pages_into_layouts
from .core.ocr import RapidOcrEngine
from .core.parser import ParseOptions, parse_image
from .core.search import ProductIndex
from .core.store import ImportMode, LayoutStore

DEFAULT_DB = os.path.join("data", "shelffinder.sqlite")

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
        for number, duplicates in layout.duplicate_pages().items():
            sources = ", ".join(os.path.basename(page.source_file) for page in duplicates)
            print(f"  ! page {number} came in {len(duplicates)} times ({sources}). "
                  f"Keep the best one and re-import, or they will both be searchable.")

    if args.db:
        from .core.library import Library

        mode = ImportMode(args.on_existing)
        library = Library(os.path.dirname(os.path.abspath(args.db)) or ".")
        try:
            for layout in layouts:
                for existing in library.store.find_matching(layout.name, layout.size):
                    print(f"  note: '{existing.title}' is already stored "
                          f"({existing.page_count} page(s), imported {existing.imported_at}) "
                          f"- importing with --on-existing {mode.value}")
                for page in layout.pages:
                    # The library keeps its own copy of every page image.
                    library.adopt_images(page, page.straightened_image, page.original_image)
                library.store.add_layout(layout, mode)
            library.reload()
            stats = library.stats()
            print(f"  stored in {library.data_dir}: {stats['products']} products in "
                  f"{stats['layouts']} layout(s)")
        finally:
            library.close()
    return 0


def _load_index(args: argparse.Namespace) -> tuple[ProductIndex, list[Layout]]:
    layouts: list[Layout] = []
    if args.json:
        with open(args.json, encoding="utf-8") as handle:
            payload = json.load(handle)
        layouts = [Layout.from_dict(item) for item in payload]
    else:
        with LayoutStore(args.db) as store:
            layouts = store.load_all()
    return ProductIndex(layouts), layouts


def _print_hit(position: int, hit) -> None:
    before, matched, after = hit.highlight()
    card = locate_hit(hit)
    print(f"\n[{position}] {before}[{matched}]{after}  {hit.product.name}")
    for line in card.summary_lines()[1:]:
        print(f"    {line}")
    if card.needs_review:
        print("    ! parsed with low confidence or shared shelves - check the sheet")


def cmd_search(args: argparse.Namespace) -> int:
    index, layouts = _load_index(args)
    if not len(index):
        print("Nothing to search yet. Parse some sheets first "
              "(shelffinder parse ... --db data/shelffinder.sqlite).", file=sys.stderr)
        return 2

    layout_ids = None
    if args.layout:
        wanted = args.layout.lower().replace(" ", "")
        layout_ids = [layout.id for layout in layouts
                      if wanted in layout.title.lower().replace(" ", "")]
        if not layout_ids:
            print(f"No layout matching '{args.layout}'. Known layouts: "
                  + ", ".join(layout.title for layout in layouts), file=sys.stderr)
            return 2

    result = index.search(args.query, layout_ids=layout_ids, limit=args.limit)
    print(result.message())
    if result.single:
        _print_hit(1, result.single)
        return 0
    for position, hit in enumerate(result.hits, start=1):
        _print_hit(position, hit)
    for hit in result.suggestions:
        card = locate_hit(hit)
        print(f"\n  did you mean {hit.product.code} ({hit.reason})? "
              f"{hit.product.name} - {card.page_label()}, {card.bay_label()}")
    return 0 if result.hits else 1


def cmd_export_pack(args: argparse.Namespace) -> int:
    from .core.library import Library

    library = Library(os.path.dirname(os.path.abspath(args.db)) or ".")
    try:
        layout_ids = None
        if args.layout:
            wanted = args.layout.lower().replace(" ", "")
            layout_ids = [layout.id for layout in library.layouts
                          if wanted in layout.title.lower().replace(" ", "")]
            if not layout_ids:
                print(f"No layout matching '{args.layout}'.", file=sys.stderr)
                return 2
        summary = library.export_pack(args.output, layout_ids=layout_ids,
                                      include_originals=args.originals,
                                      progress=lambda done, total, what: print(
                                          f"  [{done + 1}/{total}] {what}"))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        library.close()
    print(f"{args.output}: {summary.describe()}")
    return 0


def cmd_import_pack(args: argparse.Namespace) -> int:
    from .core.library import Library

    library = Library(os.path.dirname(os.path.abspath(args.db)) or ".")
    try:
        library.import_pack(args.pack, ImportMode(args.on_existing))
        stats = library.stats()
    finally:
        library.close()
    print(f"imported {args.pack}: now {stats['layouts']} layout(s), {stats['pages']} page(s), "
          f"{stats['products']} products")
    return 0


def cmd_layouts(args: argparse.Namespace) -> int:
    with LayoutStore(args.db) as store:
        listed = store.list_layouts()
    if not listed:
        print(f"No layouts stored in {args.db}.")
        return 0
    for layout in listed:
        print(f"{layout.title}: {layout.page_count} page(s), {layout.product_count} products, "
              f"imported {layout.imported_at}  [{layout.id}]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shelffinder", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    parse_cmd = sub.add_parser("parse", help="parse sheets into JSON plus debug images")
    parse_cmd.add_argument("inputs", nargs="+", help="image/PDF files, globs or folders")
    parse_cmd.add_argument("--out", default="out", help="output folder (default: out)")
    parse_cmd.add_argument("--tile-size", type=int, default=1400, help="OCR tile size")
    parse_cmd.add_argument("--pdf-dpi", type=int, default=220, help="render DPI for PDFs")
    parse_cmd.add_argument("--db", nargs="?", const=DEFAULT_DB, default=None,
                           help=f"also store the result (default path: {DEFAULT_DB})")
    parse_cmd.add_argument("--on-existing", choices=[mode.value for mode in ImportMode],
                           default=ImportMode.KEEP_BOTH.value,
                           help="what to do when the layout is already stored")
    parse_cmd.add_argument("-v", "--verbose", action="store_true")
    parse_cmd.set_defaults(func=cmd_parse)

    search_cmd = sub.add_parser("search", help="find a product by code")
    search_cmd.add_argument("query", help="three or more digits of the code")
    search_cmd.add_argument("--db", default=DEFAULT_DB, help="layout database to search")
    search_cmd.add_argument("--json", default=None,
                            help="search a layouts.json instead of the database")
    search_cmd.add_argument("--layout", default=None, help="limit to one layout")
    search_cmd.add_argument("--limit", type=int, default=20)
    search_cmd.add_argument("-v", "--verbose", action="store_true")
    search_cmd.set_defaults(func=cmd_search)

    export_cmd = sub.add_parser("export-pack",
                                help="write layouts to a pack the phone app can read")
    export_cmd.add_argument("output", help="the .zip to write")
    export_cmd.add_argument("--db", default=DEFAULT_DB)
    export_cmd.add_argument("--layout", default=None, help="export one layout only")
    export_cmd.add_argument("--originals", action="store_true",
                            help="include the original photos as well (much larger)")
    export_cmd.add_argument("-v", "--verbose", action="store_true")
    export_cmd.set_defaults(func=cmd_export_pack)

    import_cmd = sub.add_parser("import-pack", help="read a pack written elsewhere")
    import_cmd.add_argument("pack", help="the .zip to read")
    import_cmd.add_argument("--db", default=DEFAULT_DB)
    import_cmd.add_argument("--on-existing", choices=[mode.value for mode in ImportMode],
                            default=ImportMode.KEEP_BOTH.value)
    import_cmd.add_argument("-v", "--verbose", action="store_true")
    import_cmd.set_defaults(func=cmd_import_pack)

    layouts_cmd = sub.add_parser("layouts", help="list the stored layouts")
    layouts_cmd.add_argument("--db", default=DEFAULT_DB)
    layouts_cmd.add_argument("-v", "--verbose", action="store_true")
    layouts_cmd.set_defaults(func=cmd_layouts)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
