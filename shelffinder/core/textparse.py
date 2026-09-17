"""Pure text rules for planogram sheets.

Kept free of image code so it can be unit tested against strings, including the
mangled ones OCR produces ("Notch:33Depth:62cmSlope:0", "Cases 4", "C0de").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# OCR reads digits as look-alike letters.  Codes are digits only, so these are
# always safe to fold.
DIGIT_CONFUSIONS = {
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "I": "1", "l": "1", "i": "1", "|": "1", "!": "1",
    "Z": "2", "z": "2",
    "A": "4",
    "S": "5", "s": "5",
    "G": "6", "b": "6",
    "T": "7", "?": "7",
    "B": "8",
    "g": "9", "q": "9",
}

MIN_CODE_DIGITS = 4
MAX_CODE_DIGITS = 9          # the samples include 8-digit codes (10076121)

_SEPARATOR = r"[:;.,=\s]*"
# Keyword patterns tolerate the usual OCR swaps inside the word itself
# (N0tch, S1ope, Ca5es) as well as missing spaces around the separators.
_NOTCH_WORD = r"n\s*[o0]\s*[t7]\s*c\s*h"
_DEPTH_WORD = r"d\s*[e3]\s*[pn]\s*[t7]\s*h"          # "Denth" is a common misread
_SLOPE_WORD = r"s\s*[l1i]\s*[o0]\s*[pn]\s*[e3]"
_CASES_WORD = r"c\s*[a4]\s*[s5]\s*[e3]\s*[s5]?"
_NUM = r"\d{1,3}(?:[.,]\d{1,2})?"

# Numbers come back with the same swaps the codes do ("Slope:Q", "Depth:8Ocm").
# Fold those before matching, but only where a letter is clearly standing in for
# a digit, so words such as "Depth" or "Slope" survive intact.
_NUMERIC_LOOKALIKES = {"O": "0", "o": "0", "Q": "0", "l": "1", "I": "1", "|": "1",
                       "S": "5", "s": "5", "Z": "2"}

NOTCH_RE = re.compile(
    _NOTCH_WORD + _SEPARATOR + r"(?P<notch>" + _NUM + r")"
    r"(?:" + _SEPARATOR + _DEPTH_WORD + _SEPARATOR + r"(?P<depth>" + _NUM + r")\s*c?\s*m?)?"
    r"(?:" + _SEPARATOR + _SLOPE_WORD + _SEPARATOR + r"(?P<slope>-?" + _NUM + r"))?",
    re.IGNORECASE,
)
CASES_RE = re.compile(_CASES_WORD + _SEPARATOR + r"(?P<cases>" + _NUM + r")", re.IGNORECASE)


def fold_number_letters(text: str) -> str:
    """Turn letters that stand in for digits into digits.

    A letter is folded when it touches a digit ("8Ocm") or stands alone as its
    own token ("Slope:Q"); anything inside a word is left alone.
    """

    characters = list(text)
    for index, char in enumerate(characters):
        replacement = _NUMERIC_LOOKALIKES.get(char)
        if replacement is None:
            continue
        before = text[index - 1] if index else ""
        after = text[index + 1] if index + 1 < len(text) else ""
        touches_digit = before.isdigit() or after.isdigit()
        stands_alone = not before.isalpha() and not after.isalpha()
        if touches_digit or stands_alone:
            characters[index] = replacement
    return "".join(characters)


def _to_number(text: Optional[str]) -> Optional[float]:
    """Read a number that OCR may have spelled with letters ("Slope:Q")."""
    if text is None:
        return None
    negative = text.strip().startswith("-")
    folded = "".join(DIGIT_CONFUSIONS.get(char, char) for char in text.strip().lstrip("-+"))
    folded = folded.replace(",", ".")
    if not folded or not all(char.isdigit() or char == "." for char in folded):
        return None
    try:
        value = float(folded)
    except ValueError:
        return None
    return -value if negative else value
PAGE_RE = re.compile(r"(?P<page>\d{1,2})\s*(?:of|/|o f)\s*(?P<total>\d{1,2})", re.IGNORECASE)
SIZE_RE = re.compile(r"(?P<size>\d{1,2}(?:[.,]\d)?)\s*m\b", re.IGNORECASE)
MARKER_RE = re.compile(r"^[A-Z]{2,5}$")

KNOWN_MARKERS = {"NTA"}
# Boilerplate that must never be mistaken for a product name.
NOISE_SNIPPETS = (
    "customer flow", "start of customer", "contact layoutmanagement", "queries/suggestions",
    "ambient layouts", "chiller layouts", "first visible notch", "above the plinth",
    "above the base", "unstoppable",
)


@dataclass
class NotchInfo:
    notch: Optional[int] = None
    depth_cm: Optional[float] = None
    slope: Optional[float] = None
    raw: str = ""

    @property
    def complete(self) -> bool:
        return self.notch is not None and self.depth_cm is not None and self.slope is not None


def normalise_code(text: str) -> str:
    """Fold OCR letter/digit confusions and keep the digits."""
    folded = "".join(DIGIT_CONFUSIONS.get(char, char) for char in text.strip())
    return "".join(char for char in folded if char.isdigit())


def code_candidate(text: str) -> Optional[str]:
    """Return the product code if ``text`` is a stand-alone code line."""
    stripped = text.strip().strip(".,:;|-_ ")
    if not stripped or len(stripped) > MAX_CODE_DIGITS + 3:
        return None
    if CASES_RE.search(stripped) or NOTCH_RE.search(stripped):
        return None
    # Every character has to be a digit or a known digit look-alike, and most of
    # them must already be digits - that keeps words like "Glass" or "Cases" out
    # while still accepting a code read as "7OO8O38".
    if any(char not in DIGIT_CONFUSIONS and not char.isdigit() for char in stripped):
        return None
    digits = normalise_code(stripped)
    if not (MIN_CODE_DIGITS <= len(digits) <= MAX_CODE_DIGITS):
        return None
    if len(digits) != len(stripped):
        return None
    if sum(char.isdigit() for char in stripped) < len(stripped) * 0.4:
        return None
    return digits


def parse_notch(text: str) -> Optional[NotchInfo]:
    """Read a shelf's "Notch: 33 Depth:62cm Slope:0" line.

    The footer note also mentions notches ("...above the plinth is notch 4"), so
    a bare "notch N" inside a sentence is rejected: a real shelf line is short
    and carries a depth or a slope.
    """

    if is_noise(text):
        return None
    match = NOTCH_RE.search(fold_number_letters(text))
    if not match:
        return None
    if match.group("depth") is None and match.group("slope") is None:
        compact = " ".join(text.split())
        if len(compact) > 26 or not compact.lower().lstrip().startswith(("n", "1n")):
            return None
    notch = _to_number(match.group("notch"))
    if notch is None:
        return None
    return NotchInfo(
        notch=int(notch),
        depth_cm=_to_number(match.group("depth")),
        slope=_to_number(match.group("slope")),
        raw=text.strip(),
    )


def parse_cases(text: str) -> Optional[int]:
    match = CASES_RE.search(fold_number_letters(text))
    if not match:
        return None
    value = _to_number(match.group("cases"))
    return int(value) if value is not None else None


def parse_page_number(text: str) -> Optional[tuple[int, int]]:
    match = PAGE_RE.search(text)
    if not match:
        return None
    page, total = int(match.group("page")), int(match.group("total"))
    if page < 1 or total < 1 or page > total or total > 40:
        return None
    return page, total


def parse_header(text: str) -> tuple[str, str]:
    """Split "IE Household 4.5m" into ("IE Household", "4.5m")."""
    cleaned = " ".join(text.split())
    match = SIZE_RE.search(cleaned)
    if not match:
        return cleaned, ""
    size = match.group("size").replace(",", ".") + "m"
    name = cleaned[:match.start()].strip(" -,")
    return name, size


def is_marker(text: str) -> bool:
    stripped = text.strip()
    return bool(MARKER_RE.match(stripped)) and stripped.upper() not in {"OF", "CM"}


def is_noise(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return any(snippet in lowered for snippet in NOISE_SNIPPETS)


def clean_name(parts: list[str]) -> str:
    """Join the wrapped name lines of a label into one readable name."""
    cleaned: list[str] = []
    for part in parts:
        part = " ".join(part.split()).strip(" .,;|")
        if part:
            cleaned.append(part)
    name = " ".join(cleaned)
    name = re.sub(r"\s+([&/])\s*", r" \1", name)
    return re.sub(r"\s{2,}", " ", name).strip()


def near_miss_codes(code: str) -> set[str]:
    """Codes one digit away - used to suggest alternatives after a failed search."""
    out: set[str] = set()
    for index in range(len(code)):
        for digit in "0123456789":
            if digit != code[index]:
                out.add(code[:index] + digit + code[index + 1:])
    return out
