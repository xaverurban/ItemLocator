# The layout pack format

A layout pack is how a processed layout travels: desktop to desktop, or desktop
to the Android app. It carries the parse result, so nothing has to be read by
OCR a second time.

A pack is an ordinary zip:

```
household.shelfpack.zip
  pack.json                      the layouts in full
  images/<page id>.jpg           the straightened page
  images/<page id>_original.jpg  the photo it came from (only with --originals)
```

Reading one needs nothing but a zip library and a JSON parser - that is the
point of the format.

## pack.json

```jsonc
{
  "schema_version": 1,
  "exported_at": "2026-09-17T19:32:11+00:00",
  "generator": "shelffinder",
  "layouts": [
    {
      "id": "d7052d9bab86",
      "name": "IE Household",
      "size": "4.5m",
      "imported_at": "2026-09-17T17:31:03+00:00",
      "pages": [
        {
          "id": "79cad53a0ca3",
          "number": 2,
          "total_pages": 2,
          "size": [2192, 3100],          // the straightened page, in pixels
          "straightened_image": "images/79cad53a0ca3.jpg",
          "original_image": "",
          "customer_flow_reversed": false,
          "warnings": ["Bay 2 has no notch line of its own ..."],
          "tags": ["NTA"],
          "bays": [
            {
              "index": 1,                 // 1-based, left to right
              "x_range": [56.0, 632.0],
              "shelves_inherited": false, // true: borrowed from the bay to its left
              "shelves": [
                {
                  "index_from_top": 1,
                  "y_range": [234.0, 771.0],
                  "notch": 33,
                  "depth_cm": 62.0,
                  "slope": 0.0,
                  "inherited": false
                }
              ]
            }
          ],
          "products": [
            {
              "code": "7008038",
              "name": "Fairy 654ml Original",
              "cases": 4,
              "bbox": {"x": 120.0, "y": 980.0, "w": 118.0, "h": 86.0},
              "image_bbox": {"x": 96.0, "y": 812.0, "w": 168.0, "h": 268.0},
              "bay": 1,
              "shelf": 3,
              "position_left": 1,
              "position_right": 4,
              "confidence": 0.93,
              "tags": [],
              "manually_edited": false
            }
          ]
        }
      ]
    }
  ]
}
```

### The rules a reader needs

* All coordinates are pixels in the **straightened** page, whose size is
  `page.size`. Scale them by the size you draw the image at.
* `bbox` is the white label. `image_bbox` is the label plus the product's slice
  of the shelf - useful as a tap target, too large to use as a highlight.
* Bays are numbered left to right, which is customer-flow order unless
  `customer_flow_reversed` is true.
* Shelves are numbered from the top **within their bay**. Two bays can have
  different shelf counts, so to find what sits next to a product across a bay
  line, compare `y_range` bands rather than shelf numbers.
* `shelves_inherited` means the bay had no `Notch:` line of its own and was
  given the shelves of the bay to its left; treat its shelf data as unconfirmed.
* `straightened_image` may be an empty string if the page's picture was missing
  at export. Everything else still works; just do not try to draw the page.
* A reader should refuse a `schema_version` higher than it knows.

## Writing and reading one

```bash
# desktop, command line
shelffinder export-pack household.shelfpack.zip --layout "IE Household"
shelffinder import-pack household.shelfpack.zip

# desktop, app: the Packs button, or drop a .zip onto the window
# android: Layouts, then Import
```

Images are re-encoded to JPEG at 2200px on the long side, which keeps the
smallest labels readable when zoomed while keeping a two-page pack well under a
megabyte. `--originals` adds the source photos, which multiplies the size.
