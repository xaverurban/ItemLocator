"""Storage, re-import handling and the search index built from it."""

import pytest

from shelffinder.core.models import Layout
from shelffinder.core.search import ProductIndex
from shelffinder.core.store import ImportMode, LayoutStore


@pytest.fixture
def store() -> LayoutStore:
    with LayoutStore(":memory:") as opened:
        yield opened


def test_round_trip_through_sqlite(store, household_layout):
    layout_id = store.add_layout(household_layout)
    loaded = store.get_layout(layout_id)
    assert loaded is not None
    assert loaded.title == "IE Household 4.5m"
    assert [page.number for page in loaded.pages] == [1, 2]
    product = next(p for p in loaded.pages[1].products if p.code == "7008038")
    assert product.name == "Fairy 654ml Original"
    assert product.bbox is not None
    assert loaded.pages[1].bays[0].shelves[2].notch == 12


def test_listing_counts_pages_and_products(store, household_layout):
    store.add_layout(household_layout)
    listed = store.list_layouts()
    assert len(listed) == 1
    assert listed[0].page_count == 2
    assert listed[0].product_count == store.count_products()


def test_matching_ignores_ocr_spacing(store, household_layout):
    store.add_layout(household_layout)
    assert store.find_matching("IEHousehold", "4.5m")
    assert not store.find_matching("IE Frozen", "2.5m")


def test_keep_both_versions(store, household_layout):
    store.add_layout(household_layout)
    newer = Layout.from_dict(household_layout.to_dict())
    newer.id = "second"
    newer.imported_at = "2026-01-01T00:00:00+00:00"
    store.add_layout(newer, ImportMode.KEEP_BOTH)
    listed = store.list_layouts()
    assert len(listed) == 2
    assert {item.imported_at for item in listed} == {household_layout.imported_at,
                                                     "2026-01-01T00:00:00+00:00"}


def test_replace_drops_the_older_version(store, household_layout):
    store.add_layout(household_layout)
    newer = Layout.from_dict(household_layout.to_dict())
    newer.id = "second"
    newer.pages = newer.pages[:1]
    store.add_layout(newer, ImportMode.REPLACE)
    listed = store.list_layouts()
    assert len(listed) == 1
    assert listed[0].id == "second"
    assert listed[0].page_count == 1


def test_merge_replaces_only_the_pages_supplied(store, household_layout):
    layout_id = store.add_layout(household_layout)
    update = Layout.from_dict(household_layout.to_dict())
    update.id = "second"
    update.pages = [page for page in update.pages if page.number == 2]
    update.pages[0].products[0].name = "Corrected name"
    merged_id = store.add_layout(update, ImportMode.MERGE_PAGES)

    assert merged_id == layout_id
    assert len(store.list_layouts()) == 1
    loaded = store.get_layout(layout_id)
    assert [page.number for page in loaded.pages] == [1, 2]
    assert loaded.pages[1].products[0].name == "Corrected name"


def test_update_page_saves_review_edits(store, household_layout):
    layout_id = store.add_layout(household_layout)
    page = household_layout.pages[1]
    product = next(p for p in page.products if p.code == "7008038")
    product.name = "Fairy Original 654ml"
    product.manually_edited = True
    store.update_page(layout_id, page)

    reloaded = store.get_layout(layout_id)
    saved = next(p for p in reloaded.pages[1].products if p.code == "7008038")
    assert saved.name == "Fairy Original 654ml"
    assert saved.manually_edited is True


def test_delete_removes_everything(store, household_layout):
    layout_id = store.add_layout(household_layout)
    store.delete_layout(layout_id)
    assert store.list_layouts() == []
    assert store.count_products() == 0


def test_index_built_from_the_store_searches(store, household_layout, frozen_layout):
    store.add_layouts([household_layout, frozen_layout])
    index = ProductIndex(store.load_all())
    assert index.search("038").hits[0].product.code == "7008038"
    assert len(index.search("5481").hits) == 2


def test_file_backed_store_persists(tmp_path, household_layout):
    path = tmp_path / "data" / "shelffinder.sqlite"
    with LayoutStore(str(path)) as store:
        store.add_layout(household_layout)
    assert path.exists()
    with LayoutStore(str(path)) as reopened:
        assert len(reopened.list_layouts()) == 1
        assert reopened.count_products() > 0
