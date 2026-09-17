"""SQLite storage for parsed layouts.

The database holds the parsed structure only; page images stay on disk in the
data folder and are referenced by path. Search runs off an in-memory index built
from here (see :mod:`shelffinder.core.search`), so queries never touch SQL.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from .models import Bay, Layout, Page, Product, Shelf

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS layouts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    size TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    layout_id TEXT NOT NULL REFERENCES layouts(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    layout_id TEXT NOT NULL REFERENCES layouts(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS products_code ON products(code);
CREATE INDEX IF NOT EXISTS pages_layout ON pages(layout_id, number);
"""


class ImportMode(str, Enum):
    """What to do when a layout with the same name and size already exists."""

    REPLACE = "replace"        # newer version of the same layout
    KEEP_BOTH = "keep_both"    # keep the old one too, distinguished by import date
    MERGE_PAGES = "merge"      # add or overwrite individual pages of the same layout


@dataclass(frozen=True)
class ExistingLayout:
    id: str
    name: str
    size: str
    imported_at: str
    page_count: int
    product_count: int

    @property
    def title(self) -> str:
        return f"{self.name} {self.size}".strip()


def _squash(text: str) -> str:
    return "".join(char for char in text.lower() if char.isalnum())


class LayoutStore:
    """A small database of parsed layouts."""

    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        if path != ":memory:":
            folder = os.path.dirname(os.path.abspath(path))
            if folder:
                os.makedirs(folder, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(SCHEMA)
        self._connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),))
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "LayoutStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- reading ----------------------------------------------------------
    def list_layouts(self) -> list[ExistingLayout]:
        rows = self._connection.execute("""
            SELECT l.id, l.name, l.size, l.imported_at,
                   (SELECT COUNT(*) FROM pages p WHERE p.layout_id = l.id) AS page_count,
                   (SELECT COUNT(*) FROM products pr WHERE pr.layout_id = l.id) AS product_count
            FROM layouts l ORDER BY l.name, l.size, l.imported_at
        """).fetchall()
        return [ExistingLayout(row["id"], row["name"], row["size"], row["imported_at"],
                               row["page_count"], row["product_count"]) for row in rows]

    def find_matching(self, name: str, size: str) -> list[ExistingLayout]:
        """Layouts with the same name and size, ignoring OCR spacing."""
        wanted = (_squash(name), _squash(size))
        return [layout for layout in self.list_layouts()
                if (_squash(layout.name), _squash(layout.size)) == wanted]

    def get_layout(self, layout_id: str) -> Optional[Layout]:
        row = self._connection.execute("SELECT * FROM layouts WHERE id = ?",
                                       (layout_id,)).fetchone()
        if row is None:
            return None
        layout = Layout(id=row["id"], name=row["name"], size=row["size"],
                        imported_at=row["imported_at"])
        pages = self._connection.execute(
            "SELECT payload FROM pages WHERE layout_id = ? ORDER BY number, id",
            (layout_id,)).fetchall()
        layout.pages = [Page.from_dict(json.loads(page["payload"])) for page in pages]
        return layout

    def load_all(self) -> list[Layout]:
        return [layout for layout in
                (self.get_layout(existing.id) for existing in self.list_layouts())
                if layout is not None]

    # -- writing ----------------------------------------------------------
    def add_layout(self, layout: Layout, mode: ImportMode = ImportMode.KEEP_BOTH) -> str:
        """Store a layout. Returns the id it was stored under.

        ``REPLACE`` drops any layout with the same name and size first;
        ``MERGE_PAGES`` keeps the existing layout and overwrites the pages that
        carry the same page number; ``KEEP_BOTH`` always stores a new one.
        """

        existing = self.find_matching(layout.name, layout.size)
        if mode is ImportMode.REPLACE:
            for match in existing:
                self.delete_layout(match.id)
        elif mode is ImportMode.MERGE_PAGES and existing:
            target = existing[0].id
            for page in layout.pages:
                self._replace_page(target, page)
            self._connection.commit()
            return target

        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO layouts(id, name, size, imported_at) VALUES(?,?,?,?)",
                (layout.id, layout.name, layout.size, layout.imported_at))
            for page in layout.pages:
                self._insert_page(layout.id, page)
        return layout.id

    def _insert_page(self, layout_id: str, page: Page) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO pages(id, layout_id, number, payload) VALUES(?,?,?,?)",
            (page.id, layout_id, page.number, json.dumps(page.to_dict())))
        self._connection.execute("DELETE FROM products WHERE page_id = ?", (page.id,))
        self._connection.executemany(
            "INSERT OR REPLACE INTO products(id, page_id, layout_id, code, name) VALUES(?,?,?,?,?)",
            [(product.id, page.id, layout_id, product.code, product.name)
             for product in page.products])

    def _replace_page(self, layout_id: str, page: Page) -> None:
        old = self._connection.execute(
            "SELECT id FROM pages WHERE layout_id = ? AND number = ?",
            (layout_id, page.number)).fetchall()
        for row in old:
            self._connection.execute("DELETE FROM pages WHERE id = ?", (row["id"],))
        self._insert_page(layout_id, page)

    def update_page(self, layout_id: str, page: Page) -> None:
        """Save edits made on the review screen."""
        with self._connection:
            self._insert_page(layout_id, page)

    def delete_layout(self, layout_id: str) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM products WHERE layout_id = ?", (layout_id,))
            self._connection.execute("DELETE FROM pages WHERE layout_id = ?", (layout_id,))
            self._connection.execute("DELETE FROM layouts WHERE id = ?", (layout_id,))

    def add_layouts(self, layouts: Iterable[Layout],
                    mode: ImportMode = ImportMode.KEEP_BOTH) -> list[str]:
        return [self.add_layout(layout, mode) for layout in layouts]

    # -- stats ------------------------------------------------------------
    def count_products(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM products").fetchone()[0])
