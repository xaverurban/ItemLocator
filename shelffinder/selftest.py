"""A self-check the packaged app can run to prove it works.

``ShelfFinder.exe --selftest`` draws a small planogram in memory, parses it,
stores it, searches it and opens the window off-screen. If that passes, OpenCV,
the OCR models, SQLite and Qt are all present and working inside the bundle.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback

PRODUCTS = [
    ("7008038", "Fairy 654ml Original", 4),
    ("1023107", "Fairy WUL Lemon", 2),
    ("5481", "Finish Quantum", 2),
]


def _draw_sheet():
    import cv2
    import numpy as np

    width, height = 1400, 1000
    page = np.full((height, width, 3), 255, np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

    def text(value, origin, scale=0.62, weight=1):
        cv2.putText(page, value, origin, font, scale, (0, 0, 0), weight, cv2.LINE_AA)

    text("IE Selftest 1.2m", (470, 60), 1.0, 2)
    cv2.rectangle(page, (60, 120), (width - 60, height - 160), (0, 0, 0), 2)
    cv2.line(page, (760, 120), (760, height - 160), (0, 0, 0), 2)
    cv2.line(page, (60, 520), (width - 60, 520), (90, 90, 90), 1)

    text("Notch: 12 Depth:62cm Slope:0", (80, 150))
    text("Notch: 3 Depth:80cm Slope:0", (80, 550))

    for index, (code, name, cases) in enumerate(PRODUCTS):
        left = 90 + index * 420
        top = 200 if index < 2 else 600
        if index >= 2:
            left = 90
        cv2.rectangle(page, (left, top), (left + 330, top + 170), (235, 235, 235), -1)
        cv2.rectangle(page, (left + 10, top + 20), (left + 320, top + 150), (255, 255, 255), -1)
        cv2.rectangle(page, (left + 10, top + 20), (left + 320, top + 150), (60, 60, 60), 1)
        text(code, (left + 24, top + 60), 0.75, 2)
        text(name[:20], (left + 24, top + 100))
        text(f"Cases:{cases}", (left + 24, top + 136))

    text("Customer Flow ------>", (560, height - 90))
    text("1 of 1", (width - 180, height - 60))
    return page


def _check(name: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {name}{(' - ' + detail) if detail else ''}", flush=True)
    return condition


def run(verbose: bool = True) -> int:
    started = time.time()
    print("ShelfFinder self-test", flush=True)
    print(f"  python {sys.version.split()[0]}  frozen={getattr(sys, 'frozen', False)}",
          flush=True)
    results: list[bool] = []

    try:
        import cv2
        import numpy
        import onnxruntime
        print(f"  opencv {cv2.__version__}  numpy {numpy.__version__}  "
              f"onnxruntime {onnxruntime.__version__}", flush=True)
        results.append(_check("imports", True))
    except Exception as error:                                   # noqa: BLE001
        _check("imports", False, str(error))
        traceback.print_exc()
        return 1

    from .core.library import Library
    from .core.ocr import RapidOcrEngine
    from .core.parser import parse_image

    page_image = _draw_sheet()
    try:
        engine = RapidOcrEngine()
        lines = engine.read(page_image)
        results.append(_check("OCR models load and read", len(lines) > 4,
                              f"{len(lines)} lines"))
    except Exception as error:                                   # noqa: BLE001
        _check("OCR models load and read", False, str(error))
        traceback.print_exc()
        return 1

    with tempfile.TemporaryDirectory() as folder:
        try:
            page, _ = parse_image(page_image, engine, source_file="selftest.png")
            codes = {product.code for product in page.products}
            results.append(_check("parser finds the products", "7008038" in codes,
                                  f"read {sorted(codes)}"))
            notches = [shelf.notch for bay in page.bays for shelf in bay.shelves]
            results.append(_check("parser reads the notch lines", 12 in notches,
                                  f"notches {notches}"))

            image_path = os.path.join(folder, "selftest.png")
            cv2.imwrite(image_path, page_image)

            library = Library(os.path.join(folder, "library"), ocr_engine=engine)
            report = library.import_paths([image_path])
            library.commit(report)
            stats = library.stats()
            results.append(_check("library stores the page", stats["products"] > 0,
                                  f"{stats}"))

            result = library.search("038")
            results.append(_check("search finds the code",
                                  bool(result.hits) and result.hits[0].product.code == "7008038",
                                  result.message()))
            if result.hits:
                card = library.locate(result.hits[0].product, result.hits[0].page)
                results.append(_check("result card fills in",
                                      card is not None and card.bay_index >= 1,
                                      card.position_label() if card else ""))
            library.close()
        except Exception as error:                               # noqa: BLE001
            _check("parse, store and search", False, str(error))
            traceback.print_exc()
            return 1

        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtCore import qVersion

            from .ui.app import build_application
            from .ui.main_window import MainWindow
            from .ui.settings import AppSettings

            application = build_application([])
            window_library = Library(os.path.join(folder, "library2"), ocr_engine=engine)
            window_library.store.add_layout(report.layouts[0])
            window_library.reload()
            window = MainWindow(window_library, AppSettings(data_dir=window_library.data_dir))
            window.search_bar.box.setText("038")
            window.search_bar._emit()
            application.processEvents()
            shown = window.result_card.code.text()
            results.append(_check(f"window opens and shows a result (Qt {qVersion()})",
                                  shown == "7008038", f"card shows {shown!r}"))
            window.close()
        except Exception as error:                               # noqa: BLE001
            _check("window opens", False, str(error))
            traceback.print_exc()
            return 1

    passed = all(results)
    print(f"\n{'ALL CHECKS PASSED' if passed else 'SOME CHECKS FAILED'} "
          f"in {time.time() - started:.1f}s", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(run())
