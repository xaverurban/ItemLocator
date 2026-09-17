"""Render synthetic planogram sheets that mimic the printed Lidl layouts.

Two outputs per page:

* ``page_N_clean.png``  - what a good scan or PDF export looks like.
* ``page_N_photo.jpg``  - the same sheet as a phone photo: rotated 90 degrees,
  taken at an angle, with background clutter, uneven lighting, shadow, blur,
  JPEG noise and ink specks.

A ``page_N_truth.json`` with the exact expected content is written next to them
so the parser can be scored automatically.

Usage:  python tools/make_sample.py --out samples/synthetic
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sample_spec import PAGES, HEADER_CONTACT, FOOTER_NOTE  # noqa: E402

FONT_DIRS = [
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/dejavu",
    "C:/Windows/Fonts",
]
FONT_REGULAR = ["LiberationSans-Regular.ttf", "DejaVuSans.ttf", "arial.ttf"]
FONT_BOLD = ["LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf"]


def _find_font(names: list[str]) -> str:
    for directory in FONT_DIRS:
        for name in names:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                return path
    raise RuntimeError("no usable TrueType font found")


_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _find_font(FONT_BOLD if bold else FONT_REGULAR)
    key = (path, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, size)
    return _FONT_CACHE[key]


def text_size(draw: ImageDraw.ImageDraw, text: str, f) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=f)
    return box[2] - box[0], box[3] - box[1]


def wrap(draw: ImageDraw.ImageDraw, text: str, f, max_width: int, max_lines: int = 4) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if text_size(draw, trial, f)[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:max_lines]


def draw_product_photo(draw: ImageDraw.ImageDraw, box, rng: random.Random) -> None:
    """A grey blob that reads like a photocopied product photo."""
    x1, y1, x2, y2 = box
    draw.rectangle(box, fill=(238, 238, 238))
    n = max(1, int((x2 - x1) / 46))
    width = (x2 - x1) / n
    for i in range(n):
        bx = x1 + i * width + width * 0.18
        bw = width * 0.64
        top = y1 + (y2 - y1) * rng.uniform(0.08, 0.28)
        shade = rng.randint(70, 165)
        draw.rounded_rectangle([bx, top, bx + bw, y2 - 3], radius=5,
                               fill=(shade, shade, shade), outline=(40, 40, 40))
        cap_w = bw * 0.45
        draw.rectangle([bx + (bw - cap_w) / 2, top - (y2 - top) * 0.12, bx + (bw + cap_w) / 2, top],
                       fill=(55, 55, 55))


def render_page(spec: dict, dpi: int = 200, seed: int = 7) -> tuple[Image.Image, dict]:
    rng = random.Random(seed + spec["page"])
    width = int(8.27 * dpi)
    height = int(11.69 * dpi)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    scale = dpi / 200.0

    def px(value: float) -> int:
        return int(round(value * scale))

    truth: dict = {
        "layout_name": spec["layout_name"],
        "layout_size": spec["layout_size"],
        "page": spec["page"],
        "total_pages": spec["total_pages"],
        "size": [width, height],
        "bays": [],
        "products": [],
    }

    # ---------------------------------------------------------------- header
    title = f"{spec['layout_name']} {spec['layout_size']}"
    f_title = font(px(24), bold=False)
    f_small = font(px(15))
    tw = text_size(draw, title, f_title)[0]
    draw.text(((width - tw) / 2, px(48)), title, font=f_title, fill="black")
    tw = text_size(draw, HEADER_CONTACT, f_small)[0]
    draw.text(((width - tw) / 2, px(86)), HEADER_CONTACT, font=f_small, fill="black")

    if spec["page"] == 1:
        draw.text((px(60), px(150)), "Start of customer flow", font=font(px(16)), fill="black")

    # ------------------------------------------------------------------ grid
    grid_x1, grid_x2 = px(60), width - px(60)
    grid_y1, grid_y2 = px(190), height - px(210)
    draw.rectangle([grid_x1, grid_y1, grid_x2, grid_y2], outline=(30, 30, 30), width=max(1, px(2)))

    bays = spec["bays"]
    bay_width = (grid_x2 - grid_x1) / len(bays)

    for bay_index, bay in enumerate(bays, start=1):
        bx1 = grid_x1 + (bay_index - 1) * bay_width
        bx2 = bx1 + bay_width
        if bay_index > 1:
            draw.line([bx1, grid_y1, bx1, grid_y2], fill=(30, 30, 30), width=max(1, px(2)))

        shelves = bay["shelves"]
        band_height = (grid_y2 - grid_y1) / len(shelves)
        bay_truth = {"index": bay_index, "x_range": [bx1, bx2], "shelves": [],
                     "shelves_inherited": bool(bay.get("share_shelves_with_previous_bay"))}

        for shelf_index, (notch, depth, slope, products) in enumerate(shelves, start=1):
            sy1 = grid_y1 + (shelf_index - 1) * band_height
            sy2 = sy1 + band_height
            if shelf_index > 1:
                draw.line([bx1, sy1, bx2, sy1], fill=(90, 90, 90), width=max(1, px(1)))

            notch_text = f"Notch: {notch} Depth:{depth}cm Slope:{slope}"
            f_notch = font(px(13))
            show_notch = not bay.get("share_shelves_with_previous_bay")
            if show_notch:
                draw.text((bx1 + px(6), sy1 + px(4)), notch_text, font=f_notch, fill="black")
            bay_truth["shelves"].append({
                "index_from_top": shelf_index, "notch": notch, "depth_cm": depth,
                "slope": slope, "y_range": [sy1, sy2],
            })

            if not products:
                continue

            content_y1 = sy1 + (px(22) if show_notch else px(6))
            content_y2 = sy2 - px(6)
            cell_width = (bx2 - bx1 - px(10)) / len(products)

            for pos, product in enumerate(products, start=1):
                code, name, cases = product[0], product[1], product[2]
                options = product[3] if len(product) > 3 else {}
                tiny = bool(options.get("tiny"))

                cx1 = bx1 + px(5) + (pos - 1) * cell_width
                cx2 = cx1 + cell_width - px(3)
                draw_product_photo(draw, [cx1, content_y1, cx2, content_y2], rng)

                f_code = font(px(7 if tiny else 12), bold=False)
                f_name = font(px(7 if tiny else 11))
                pad = px(3)
                label_w = min(cell_width - px(8), px(50 if tiny else 120))
                name_lines = wrap(draw, name, f_name, int(label_w - 2 * pad), max_lines=4)
                line_h = text_size(draw, "Ag", f_name)[1] + px(3)
                code_h = text_size(draw, code, f_code)[1] + px(3)
                label_h = code_h + line_h * (len(name_lines) + 1) + 2 * pad

                lx1 = cx1 + (cx2 - cx1 - label_w) / 2
                ly1 = content_y1 + (content_y2 - content_y1 - label_h) / 2
                lx2, ly2 = lx1 + label_w, ly1 + label_h
                draw.rectangle([lx1, ly1, lx2, ly2], fill="white", outline=(60, 60, 60))

                ty = ly1 + pad
                draw.text((lx1 + pad, ty), code, font=f_code, fill="black")
                ty += code_h
                for line in name_lines:
                    draw.text((lx1 + pad, ty), line, font=f_name, fill="black")
                    ty += line_h
                draw.text((lx1 + pad, ty), f"Cases:{cases}", font=f_name, fill="black")

                truth["products"].append({
                    "code": code, "name": name, "cases": cases,
                    "bay": bay_index, "shelf": shelf_index,
                    "position_left": pos, "position_right": len(products) - pos + 1,
                    "notch": notch, "depth_cm": depth, "slope": slope,
                    "bbox": [lx1, ly1, lx2 - lx1, ly2 - ly1],
                    "tiny": tiny,
                })

        if bay.get("marker"):
            draw.text((bx1 + px(10), grid_y2 + px(12)), bay["marker"], font=font(px(14), bold=True),
                      fill="black")
        truth["bays"].append(bay_truth)

    # ---------------------------------------------------------------- footer
    f_foot = font(px(14))
    y = grid_y2 + px(46)
    for line in wrap(draw, FOOTER_NOTE, f_foot, int(width * 0.42)):
        draw.text((px(60), y), line, font=f_foot, fill="black")
        y += px(20)
    arrow_y = grid_y2 + px(70)
    draw.text((width * 0.5 - px(60), arrow_y - px(22)), "----------------->>",
              font=f_foot, fill="black")
    draw.text((width * 0.5 - px(40), arrow_y), "Customer Flow", font=f_foot, fill="black")
    page_text = f"{spec['page']} of {spec['total_pages']}"
    draw.text((width - px(130), height - px(60)), page_text, font=f_foot, fill="black")

    return img, truth


# ------------------------------------------------------------------ photo sim
def simulate_photo(img: Image.Image, seed: int = 11, rotate: int = 90) -> Image.Image:
    import cv2

    rng = np.random.default_rng(seed)
    page = np.array(img)[:, :, ::-1].copy()
    # A phone photo frames the sheet at roughly this many pixels on the long side.
    target_long = 3400
    scale = target_long / float(max(page.shape[:2])) / 1.35
    page = cv2.resize(page, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ph, pw = page.shape[:2]

    canvas_h, canvas_w = int(ph * 1.35), int(pw * 1.5)
    canvas = np.full((canvas_h, canvas_w, 3), 150, np.uint8)
    # Cluttered desk background: tiles and a dark object in a corner.
    for gy in range(0, canvas_h, 90):
        cv2.line(canvas, (0, gy), (canvas_w, gy), (128, 128, 128), 2)
    for gx in range(0, canvas_w, 90):
        cv2.line(canvas, (gx, 0), (gx, canvas_h), (128, 128, 128), 2)
    cv2.rectangle(canvas, (0, 0), (int(canvas_w * 0.22), int(canvas_h * 0.30)), (35, 35, 38), -1)
    canvas = cv2.add(canvas, rng.normal(0, 6, canvas.shape).astype(np.int16).clip(-40, 40)
                     .astype(np.uint8))

    src = np.float32([[0, 0], [pw, 0], [pw, ph], [0, ph]])
    ox, oy = (canvas_w - pw) / 2, (canvas_h - ph) / 2
    jitter = lambda: rng.uniform(-0.028, 0.028)  # noqa: E731
    dst = np.float32([
        [ox + pw * jitter(), oy + ph * jitter()],
        [ox + pw * (1 + jitter()), oy + ph * jitter()],
        [ox + pw * (1 + jitter()), oy + ph * (1 + jitter())],
        [ox + pw * jitter(), oy + ph * (1 + jitter())],
    ])
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(page, matrix, (canvas_w, canvas_h), borderValue=(255, 255, 255))
    mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), matrix, (canvas_w, canvas_h))
    out = np.where(mask[:, :, None] > 0, warped, canvas).astype(np.uint8)

    # Uneven lighting plus a soft shadow along one edge.
    yy, xx = np.mgrid[0:canvas_h, 0:canvas_w].astype(np.float32)
    light = 0.78 + 0.34 * (1 - ((xx / canvas_w - 0.35) ** 2 + (yy / canvas_h - 0.4) ** 2))
    shadow = 1 - 0.30 * np.clip((xx / canvas_w - 0.72) / 0.28, 0, 1)
    out = np.clip(out.astype(np.float32) * (light * shadow)[:, :, None], 0, 255).astype(np.uint8)

    # Ink specks and dust.
    for _ in range(90):
        cx, cy = int(rng.uniform(0, canvas_w)), int(rng.uniform(0, canvas_h))
        cv2.circle(out, (cx, cy), int(rng.uniform(1, 4)), (30, 30, 30), -1)

    out = cv2.GaussianBlur(out, (3, 3), 0.7)
    out = np.clip(out.astype(np.int16) + rng.normal(0, 4, out.shape).astype(np.int16),
                  0, 255).astype(np.uint8)
    if rotate:
        code = {90: cv2.ROTATE_90_COUNTERCLOCKWISE, 180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_CLOCKWISE}[rotate]
        out = cv2.rotate(out, code)
    return Image.fromarray(out[:, :, ::-1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="samples/synthetic")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--no-photo", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    for spec in PAGES:
        img, truth = render_page(spec, dpi=args.dpi)
        base = os.path.join(args.out, f"page_{spec['page']}")
        img.save(f"{base}_clean.png")
        with open(f"{base}_truth.json", "w", encoding="utf-8") as fh:
            json.dump(truth, fh, indent=2)
        print(f"wrote {base}_clean.png ({len(truth['products'])} products)")
        if not args.no_photo:
            rotate = 90 if spec["page"] == 1 else 270
            simulate_photo(img, seed=11 + spec["page"], rotate=rotate).save(
                f"{base}_photo.jpg", quality=72)
            print(f"wrote {base}_photo.jpg (rotated {rotate})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
