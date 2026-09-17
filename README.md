# ShelfFinder

Find where a product goes on a printed shelf layout sheet (planogram).

Type part of a product code and get the page, bay, shelf and position it belongs
on, with the product highlighted on the sheet. Works fully offline: the sheets
are internal store documents and never leave the machine.

**Status: phase 3 (desktop app).** A dark, keyboard-driven desktop app that
imports sheets, searches codes as you type and shows the product highlighted on
the page - plus the command line tool underneath it. The review and edit screen
comes in phase 4.

---

## Install

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
```

Python 3.11 or newer. First run downloads nothing - the OCR models ship inside
`rapidocr-onnxruntime`.

## Run the app

```bash
.venv/bin/python -m shelffinder            # Windows: .venv\Scripts\python -m shelffinder
```

Drop photos, scans or PDFs onto the window (or press Ctrl+O). Each page is
straightened, read and stored; the progress bar reports page by page. Then type
three or more digits of a code.

* **One match** jumps straight to it: the page opens, the view zooms to the
  product, the product is outlined in the highlight colour with a soft glow and
  the rest of the page dims. Its shelf row and bay are faintly outlined too.
* **Several matches** drop a list under the search box, matched digits in bold,
  with the name, layout, page, bay, shelf and position. Arrow keys move, Enter
  opens, and each row previews as you move.
* **No match** offers the near misses - a wrong digit or two swapped.
* **Clicking any product on the sheet** shows its card instead (reverse lookup).
* **Original photo** switches between the straightened page and the photo it
  came from, with the highlight mapped onto both through the page transform.
* Scroll to zoom, drag to pan, double-click to fit, pinch on a touchscreen.

| Shortcut | What it does |
| --- | --- |
| `Ctrl+O` | import sheets |
| `Ctrl+F` or `/` | focus the search box |
| `Enter` | open the top result |
| `Esc` | clear the search and the highlight |
| `←` `→` | previous / next page |
| `Ctrl+B` | show or hide the layouts panel |
| `Ctrl+,` | settings |

Settings cover the highlight colour, the UI accent colour, how much the rest of
the page dims, which layout to search by default, and where the data folder
lives. Re-importing a layout that is already stored asks whether to replace it,
update just those pages, or keep both, showing the import dates.

## The Android app

`mobile/` is a Flutter app that reads layout packs exported by the desktop. It
does no OCR: the desktop has already done that, so the phone only has to search
and show. It works with no signal, and nothing leaves the device.

Get the APK the same way as the Windows build: **Actions → Android build → the
newest green run → Artifacts → `ShelfFinder-android`**. Copy `ShelfFinder.apk`
to the phone and open it; Android will ask you to allow installing from that
source.

Sheets get onto the phone two ways - **Layouts → Add sheets**:

* **A layout pack from the desktop.** Export one with **Packs → Export a layout
  pack**, copy the `.zip` across, and import it. This is the accurate route: the
  desktop has flattened the page and read it carefully, and importing takes a
  second.
* **Photograph a sheet, or pick photos from the gallery.** The phone reads them
  itself, offline, with on-device OCR. It has no OpenCV, so it cannot flatten a
  page or correct perspective: lay the sheet flat, fill the frame and keep the
  camera square on. Products read this way are tagged `phone-import` and carry a
  lower confidence, and the app says plainly that it is rougher than the desktop.

* Search is the same as the desktop: three digits or more, ends-with before
  contains, near misses when nothing matches.
* A result opens the page zoomed onto that product, dimmed around it, with the
  bay, shelf, notch, position, cases and both neighbours underneath.
* Tapping any product on the sheet shows its card instead.
* Pinch to zoom, drag to pan.

Working on it:

```bash
cd mobile
flutter pub get
flutter analyze
flutter test          # 50 tests, including one that reads a real exported pack
flutter build apk --release
```

Reading a photo on the phone follows the same shape as the desktop, with what
is possible in pure Dart: on-device OCR for the text, a scan for the printed
bay dividers and shelf rules (a bay divider is a column of the image that is far
darker than its neighbours over most of the page), the same notch/code/cases
rules, and the same "a bay with no notch line of its own borrows the one to its
left". Orientation is settled the same way too - by the shape of the text boxes,
then by which way the notch numbers count.

The pack format is written down in [docs/layout-pack.md](docs/layout-pack.md) -
a zip holding one JSON document and the page images, readable with nothing but a
zip library and a JSON parser.

## Getting the Windows app

Every push builds it on a Windows runner, tests it, self-tests the packaged
executable and uploads it: **Actions → Windows build → the newest green run →
Artifacts → `ShelfFinder-windows`**. Unzip it anywhere and double-click
`ShelfFinder.exe`.

Windows will warn about an unknown publisher because the build is not
code-signed - choose *More info*, then *Run anyway*.

If the window does not appear, run `ShelfFinder-console.exe` from a command
prompt to see the error, or `ShelfFinder-console.exe --selftest` to check the
build itself: it draws a small planogram, parses it, stores it, searches it and
opens the window off-screen, printing a pass or fail for each step.

### Building it yourself

```bash
pip install -r requirements.txt pyinstaller
pip uninstall -y opencv-python                      # RapidOCR pulls in the heavy build
pip install --force-reinstall --no-deps opencv-python-headless
pyinstaller packaging/shelffinder.spec --noconfirm --clean
dist/ShelfFinder/ShelfFinder-console --selftest
```

One folder rather than one file, so start-up stays quick. It comes to roughly
300-500 MB unpacked, most of it Qt, OpenCV and the OCR models, and it runs with
no network access at all.

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
.venv/bin/python -m pytest             # 95 fast unit tests
.venv/bin/python -m pytest -m ui       # 19 UI tests, headless
.venv/bin/python -m pytest -m slow     # 11 end-to-end, loads the OCR models (~20s)
```

The UI tests run against a real main window on Qt's offscreen platform, so they
cover the things that are easy to break by hand: the card's numbers, the
single-match jump, the near-miss list, the dim overlay, reverse lookup, page
navigation and the panels stacking on a narrow window.

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
    library.py     the data folder: import, store, search, edit
  ui/              PySide6, and nothing in core imports from here
    app.py         entry point
    main_window.py sidebar, search, viewer and result card wired together
    viewer.py      zoom, pan, highlight with dim, mapped onto either image
    search_bar.py  debounced search box and the result list
    result_card.py the big numbers
    sidebar.py     layouts, pages and the thumbnail strip
    import_task.py the import worker thread
    settings.py    settings_dialog.py  theme.py
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
3. ~~Desktop UI: import, viewer, search, highlight~~ - done
4. Review and edit screen - next
5. ~~Layout pack export/import, Windows `.exe`~~ - done (settings already in)
6. ~~Android app~~ - done; iOS is the same codebase when wanted
