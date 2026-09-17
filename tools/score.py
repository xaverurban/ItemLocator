"""Score parser output against the synthetic ground truth.

    python tools/score.py --parsed out --truth samples/synthetic
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from difflib import SequenceMatcher


def norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def score_page(parsed: dict, truth: dict) -> dict:
    truth_products = {p["code"]: p for p in truth["products"]}
    parsed_products: dict[str, list[dict]] = {}
    for product in parsed["products"]:
        parsed_products.setdefault(product["code"], []).append(product)

    found = missing = 0
    placed = name_ok = cases_ok = 0
    name_similarity: list[float] = []
    problems: list[str] = []

    for code, expected in truth_products.items():
        candidates = parsed_products.get(code)
        if not candidates:
            missing += 1
            problems.append(f"MISSING {code} {expected['name'][:34]!r}")
            continue
        found += 1
        # Compare against the candidate nearest the expected label position.
        best = min(candidates, key=lambda c: abs((c["bbox"] or {"x": 0})["x"] - expected["bbox"][0])
                   + abs((c["bbox"] or {"y": 0})["y"] - expected["bbox"][1]))
        if (best["bay"] == expected["bay"] and best["shelf"] == expected["shelf"]
                and best["position_left"] == expected["position_left"]):
            placed += 1
        else:
            problems.append(
                f"PLACE   {code}: got bay {best['bay']} shelf {best['shelf']} "
                f"pos {best['position_left']}, expected bay {expected['bay']} "
                f"shelf {expected['shelf']} pos {expected['position_left']}")
        similarity = SequenceMatcher(None, norm_name(best["name"]),
                                     norm_name(expected["name"])).ratio()
        name_similarity.append(similarity)
        if similarity >= 0.9:
            name_ok += 1
        elif similarity < 0.75:
            problems.append(f"NAME    {code}: {best['name']!r} != {expected['name']!r}")
        if best.get("cases") == expected["cases"]:
            cases_ok += 1
        else:
            problems.append(f"CASES   {code}: got {best.get('cases')} expected {expected['cases']}")

    spurious = [code for code in parsed_products if code not in truth_products]
    total = len(truth_products)

    # Shelf metadata: every notch line present with the right depth/slope.
    def notch_key(shelf: dict) -> tuple:
        return tuple(-1 if value is None else float(value)
                     for value in (shelf.get("notch"), shelf.get("depth_cm"), shelf.get("slope")))

    expected_notches = sorted((notch_key(s) for bay in truth["bays"] for s in bay["shelves"]
                               if not bay.get("shelves_inherited")))
    got_notches = sorted((notch_key(s) for bay in parsed["bays"] for s in bay["shelves"]
                          if not s.get("inherited")))

    return {
        "total": total, "found": found, "missing": missing, "placed": placed,
        "name_ok": name_ok, "cases_ok": cases_ok, "spurious": spurious,
        "mean_name_similarity": sum(name_similarity) / max(len(name_similarity), 1),
        "page_number_ok": parsed.get("number") == truth["page"]
        and parsed.get("total_pages") == truth["total_pages"],
        "layout_ok": norm_name(parsed.get("layout_name", "") + parsed.get("layout_size", ""))
        == norm_name(truth["layout_name"] + truth["layout_size"]),
        "bays_ok": len(parsed.get("bays", [])) == len(truth["bays"]),
        "notches_expected": expected_notches, "notches_got": got_notches,
        "problems": problems,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed", default="out")
    ap.add_argument("--truth", default="samples/synthetic")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    overall = {"total": 0, "found": 0, "placed": 0, "name_ok": 0, "cases_ok": 0}
    for truth_path in sorted(glob.glob(os.path.join(args.truth, "page_*_truth.json"))):
        page_number = os.path.basename(truth_path).split("_")[1]
        truth = json.load(open(truth_path, encoding="utf-8"))
        for parsed_path in sorted(glob.glob(os.path.join(args.parsed, f"page_{page_number}_*.json"))):
            if parsed_path.endswith("_truth.json"):
                continue
            parsed = json.load(open(parsed_path, encoding="utf-8"))
            result = score_page(parsed, truth)
            for key in overall:
                overall[key] += result[key]
            print(f"\n=== {os.path.basename(parsed_path)} ===")
            print(f"  products : {result['found']}/{result['total']} found, "
                  f"{result['placed']}/{result['total']} placed correctly, "
                  f"{len(result['spurious'])} spurious")
            print(f"  names    : {result['name_ok']}/{result['total']} exact "
                  f"(mean similarity {result['mean_name_similarity']:.2f})")
            print(f"  cases    : {result['cases_ok']}/{result['total']}")
            print(f"  header   : layout {'ok' if result['layout_ok'] else 'WRONG'}, "
                  f"page number {'ok' if result['page_number_ok'] else 'WRONG'}, "
                  f"bays {'ok' if result['bays_ok'] else 'WRONG'}")
            print(f"  notches  : expected {result['notches_expected']}")
            print(f"             got      {result['notches_got']}")
            if not args.quiet:
                for problem in result["problems"][:25]:
                    print(f"    - {problem}")
                if result["spurious"]:
                    print(f"    - SPURIOUS codes: {result['spurious']}")

    print(f"\nTOTAL: {overall['found']}/{overall['total']} found, "
          f"{overall['placed']}/{overall['total']} placed, "
          f"{overall['name_ok']}/{overall['total']} names, "
          f"{overall['cases_ok']}/{overall['total']} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
