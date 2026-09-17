# ShelfFinder

Find where a product goes on a printed shelf layout sheet (planogram).

Type part of a product code and get the page, bay, shelf and position it belongs
on, with the product highlighted on the sheet. Works fully offline: the sheets
are internal store documents and never leave the machine.

**Status: phase 2 (search).** A command line tool that turns photos, scans and
PDFs of layout sheets into straightened pages, debug overlays and JSON, stores
them in SQLite, and answers code searches with the full shelf location. The
desktop UI comes in phase 3.

---

## Install

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
```

Python 3.11 or newer. First run downloads nothing - the OCR models ship inside
`rapidocr-onnxruntime`.

## Parse some sheets

```bash
.venv/bin/python -m shelffinder.cli parse "photos/*.jpg" --out out
```

Accepts JPG, PNG, HEIC, TIFF, WEBP and PDF (every page of a PDF is parsed), plus
folders and globs. For each page it writes into `--out`:

| File | What it is |
| --- | --- |
| `<name>_straight.png` | the sheet, cropped out of the photo, flattened and turned upright |
| `<name>_overlay.png` | the same page with the detected bays, shelves and products drawn on |
| `<name>.json` | the parsed page: bays, shelves, products, confidences, warnings |
| `layouts.json` | all pages grouped into layouts and ordered by page number |

The overlay is the thing to look at first: orange = bay, green = shelf band with
its notch/depth/slope, yellow = product label with `bay/shelf/position`, red =
low confidence, which is what the phase 4 review screen will ask you to check.

## Find a product

Parsing with `--db` stores the layouts, and `search` answers questions about them.

```bash
.venv/bin/python -m shelffinder.cli parse "photos/*.jpg" --out out --db
.venv/bin/python -m shelffinder.cli search 038
```

```
1 match.

[1] 7008[038]  Fairy 654ml Original
    IE Household 4.5m, page 2 of 2
    Bay 1 of 3
    Shelf 3 from top, 2 from bottom (Notch 12, depth 62cm, slope 0)
    Position 1 from left, 4 from right of 4
    Cases: 4
    Neighbours - right: 1023107 Fairy WUL Lemon
```

* `search <digits>` needs three digits or more, and ignores anything that is not
  a digit, so a typed `O` still finds a `0`.
* Matches are ranked **exact code, then code ends with, then code contains**.
* A code that appears on several shelves or in several layouts lists every
  location.
* No match reports what was searched ("No product ending in 999") and suggests
  codes one digit different or with two digits swapped - which is what an OCR
  slip usually looks like.
* `--layout "IE Household"` limits the search to one layout; the default is all
  of them. `--json out/layouts.json` searches a parse output without a database.
* `shelffinder layouts` lists what is stored, with import dates.
* Re-importing a layout that is already stored: `--on-existing keep_both`
  (default), `replace`, or `merge` to overwrite just the pages supplied.

## Try it without your own sheets

`tools/make_sample.py` renders two synthetic sheets modelled on the real
"IE Household 4.5m" pages - same bay and shelf structure, same codes, including
the tiny labels and the bays that carry no notch line of their own. It writes a
clean scan, a simulated phone photo (rotated, at an angle, uneven light, ink
specks, background clutter) and the ground truth for each page.

```bash
.venv/bin/python tools/make_sample.py --out samples/synthetic
.venv/bin/python -m shelffinder.cli parse "samples/synthetic/*" --out out
.venv/bin/python tools/score.py --parsed out --truth samples/synthetic
```

Current score on those sheets: **128/130 products found and placed on the right
bay, shelf and position**, every notch line read, headers and page numbers
correct. The two misses are the smallest labels on the simulated *photo*; the
same labels read correctly on the scan.

## Tests

```bash
.venv/bin/python -m pytest             # fast unit tests
.venv/bin/python -m pytest -m slow     # end-to-end, loads the OCR models (~30s)
```

There are 95 fast tests covering the text rules, the parser internals, the data
model, storage, search ranking and the result card, and 11 slow ones.

The slow tests are the acceptance tests from the brief: "038" is the leftmost
product on the notch 12 shelf of page 2, "5481" is the rightmost on the top
shelf, "1060" is on the bottom shelf of the first bay of page 1, "167" is on
page 1, and every `Notch:` line is matched to the right shelf - and the same
searches are then run over the parsed output.

### How search is put together

`ProductIndex` keeps every product from every layout in memory - a few thousand
rows at most - so a keystroke is a linear scan and nothing waits on SQL. SQLite
is the store, not the query engine. A `SearchHit` carries where in the code the
query matched, so the UI can embolden those digits, and `locate()` turns a hit
into the card: bay N of total in customer-flow order, shelf N from the top and
from the bottom with its notch, depth and slope, position N from left and right
within that bay's shelf, cases, and the products either side.

Neighbours are worked out from shelf **height bands**, not shelf numbers: bays
number their shelves independently, so the product to the right of the last one
in a bay is found by looking for the shelf in the next bay whose band lines up,
and the card says "(next bay)" when it crosses the line. If the customer-flow
arrow on a sheet ever points left, `customer_flow_reversed` flips the bay
numbering and the left/right neighbours with it.

---

## How a page is parsed

1. **Find the sheet.** Candidate quadrilaterals come from edges and from
   brightness; each is scored on A4 aspect, paper brightness, contrast against
   the background and how much of its outline sits on a real image edge. The
   best one is perspective-corrected to a flat A4 page.
2. **Turn it upright.** The page shape narrows it to two rotations; a quick OCR
   pass on each picks the one that reads like a planogram (`Notch`, `Depth`,
   `Cases`, `Customer Flow`).
3. **Read the page.** OCR runs in overlapping tiles, because the detector
   downscales whole-page input and loses the smallest labels.
4. **Find the grid.** Long vertical rules become bay dividers, horizontal rules
   become shelf edges; broken rules are joined across gaps.
5. **Read the shelves.** Every `Notch: 33 Depth:62cm Slope:0` line is matched to
   its bay and its shelf band. Sheets put that line at the top or the bottom of
   the row it describes, so both readings are tested and the one that leaves no
   product stranded wins. A bay with no notch line of its own inherits the
   shelves of the bay to its left and is flagged for review.
6. **Read the labels.** OCR lines are grouped into labels - a code, the name
   wrapped over up to four lines, then `Cases:N`.
7. **Second look.** Doubtful labels and any print the first pass did not cover
   are re-read zoomed in, at a magnification chosen from the measured text
   height. Print that still cannot be read becomes an empty entry tagged
   `unreadable` rather than being dropped silently.
8. **Place everything.** Each product gets its bay, its shelf and its position
   from the left and from the right within that bay's shelf.

### Built for OCR mistakes

Codes are digits only, so `O/0`, `I/l/1`, `B/8` and `S/5` are folded before a
code is accepted, and a token is only treated as a code if every character is a
digit or a known look-alike - `Glass` and `Cases` are not codes. The same folding
applies to numbers inside notch lines (`Slope:Q`, `Depth:8Ocm`), and the
keywords themselves tolerate misreads (`N0tch`, `Denth`, `S1ope`) and the
missing spaces OCR often produces (`Notch:33Depth:62cmSlope:0`). The footer note
that mentions "notch 4" and "notch 1" is explicitly not a shelf line.

## Layout of the code

```
shelffinder/
  core/            no UI imports anywhere in here - reusable by a phone app
    models.py      Layout / Page / Bay / Shelf / Product, JSON in and out
    imaging.py     loading, page detection, perspective correction, rotation
    ocr.py         OCR abstraction plus the RapidOCR backend
    structure.py   bay dividers and shelf rules
    textparse.py   notch / cases / code / header rules, OCR-tolerant
    parser.py      puts a page together
    render.py      debug overlays
    store.py       SQLite persistence and re-import handling
    search.py      the code index and matching rules
    locate.py      a hit turned into the result card, neighbours included
  cli.py           the command line front end
tools/
  make_sample.py   synthetic sheets that mimic the real ones
  sample_spec.py   their content, transcribed from the real sheets
  score.py         parser output against ground truth
```

`core` never imports a GUI toolkit, so the same parsing and data model can be
reused behind a desktop UI, a phone app or a batch job.

## Roadmap

1. ~~Parser prototype (CLI, straightened pages, overlays, JSON)~~ - done
2. ~~Search logic with unit tests~~ - done
3. Desktop UI: import, viewer, search, highlight
4. Review and edit screen
5. Settings, layout pack export/import, Windows `.exe`
6. Phone app recommendation
