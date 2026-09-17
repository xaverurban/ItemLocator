"""Layout packs: the zip that carries a processed layout to another machine."""

import json
import os
import zipfile

import cv2
import numpy as np
import pytest

from shelffinder.core.pack import (PACK_JSON, PACK_SCHEMA_VERSION, export_pack,
                                   import_pack, read_pack_manifest)


@pytest.fixture
def layout_with_images(tmp_path, household_layout):
    folder = tmp_path / "images"
    folder.mkdir()
    for page in household_layout.pages:
        image = np.full((3000, 2100, 3), 230, np.uint8)
        cv2.putText(image, f"page {page.number}", (100, 400), cv2.FONT_HERSHEY_SIMPLEX,
                    6, (10, 10, 10), 8)
        path = folder / f"{page.id}.png"
        cv2.imwrite(str(path), image)
        page.straightened_image = str(path)
        page.original_image = str(path)
    return household_layout


def test_export_then_import_round_trip(tmp_path, layout_with_images):
    destination = str(tmp_path / "household.shelfpack.zip")
    summary = export_pack([layout_with_images], destination)

    assert summary.pages == 2
    assert summary.products == sum(len(page.products) for page in layout_with_images.pages)
    assert os.path.getsize(destination) > 0
    assert "MB" in summary.describe()

    imported = import_pack(destination, str(tmp_path / "unpacked"))
    assert len(imported) == 1
    restored = imported[0]
    assert restored.title == layout_with_images.title
    assert [page.number for page in restored.pages] == [1, 2]

    original_product = layout_with_images.pages[1].products[0]
    restored_product = restored.pages[1].products[0]
    assert restored_product.code == original_product.code
    assert restored_product.bbox.as_tuple() == original_product.bbox.as_tuple()
    assert restored.pages[1].bays[0].shelves[0].notch == \
        layout_with_images.pages[1].bays[0].shelves[0].notch


def test_images_are_extracted_and_readable(tmp_path, layout_with_images):
    destination = str(tmp_path / "pack.zip")
    export_pack([layout_with_images], destination)
    imported = import_pack(destination, str(tmp_path / "unpacked"))
    for page in imported[0].pages:
        assert os.path.exists(page.straightened_image)
        assert cv2.imread(page.straightened_image) is not None


def test_images_are_downscaled_for_a_phone(tmp_path, layout_with_images):
    destination = str(tmp_path / "pack.zip")
    export_pack([layout_with_images], destination, long_side=800)
    imported = import_pack(destination, str(tmp_path / "unpacked"))
    image = cv2.imread(imported[0].pages[0].straightened_image)
    assert max(image.shape[:2]) == 800


def test_originals_are_left_out_by_default(tmp_path, layout_with_images):
    plain = str(tmp_path / "plain.zip")
    with_originals = str(tmp_path / "full.zip")
    export_pack([layout_with_images], plain)
    export_pack([layout_with_images], with_originals, include_originals=True)

    with zipfile.ZipFile(plain) as archive:
        assert not [name for name in archive.namelist() if name.endswith("_original.jpg")]
    with zipfile.ZipFile(with_originals) as archive:
        assert [name for name in archive.namelist() if name.endswith("_original.jpg")]
    assert os.path.getsize(with_originals) > os.path.getsize(plain)


def test_manifest_is_plain_json_a_phone_can_read(tmp_path, layout_with_images):
    destination = str(tmp_path / "pack.zip")
    export_pack([layout_with_images], destination)
    with zipfile.ZipFile(destination) as archive:
        payload = json.loads(archive.read(PACK_JSON))

    assert payload["schema_version"] == PACK_SCHEMA_VERSION
    assert payload["exported_at"]
    page = payload["layouts"][0]["pages"][0]
    assert page["straightened_image"].startswith("images/")
    product = page["products"][0]
    assert {"code", "name", "cases", "bay", "shelf", "position_left", "bbox"} <= set(product)


def test_a_newer_pack_is_refused_with_a_clear_message(tmp_path, layout_with_images):
    destination = str(tmp_path / "pack.zip")
    export_pack([layout_with_images], destination)
    # Rewrite the manifest as if a future version had written it.
    with zipfile.ZipFile(destination) as archive:
        payload = json.loads(archive.read(PACK_JSON))
        others = [(name, archive.read(name)) for name in archive.namelist()
                  if name != PACK_JSON]
    payload["schema_version"] = PACK_SCHEMA_VERSION + 5
    with zipfile.ZipFile(destination, "w") as archive:
        archive.writestr(PACK_JSON, json.dumps(payload))
        for name, data in others:
            archive.writestr(name, data)

    with pytest.raises(ValueError, match="newer version"):
        read_pack_manifest(destination)


def test_a_page_with_a_missing_image_still_imports(tmp_path, layout_with_images):
    layout_with_images.pages[0].straightened_image = str(tmp_path / "gone.png")
    destination = str(tmp_path / "pack.zip")
    export_pack([layout_with_images], destination)
    imported = import_pack(destination, str(tmp_path / "unpacked"))
    assert imported[0].pages[0].straightened_image == ""
    assert imported[0].pages[1].straightened_image != ""
