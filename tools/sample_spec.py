"""Ground-truth content for the synthetic test sheets.

Transcribed from the two photographed Lidl "IE Household 4.5m" sheets, so the
synthetic pages exercise the same shapes the real ones do: bays with different
shelf counts, a bay with no notch line of its own, tiny labels, names that wrap
over several lines, and the same code appearing on more than one shelf.
"""

from __future__ import annotations

# A shelf is (notch, depth_cm, slope, [products]).
# A product is (code, name, cases) or (code, name, cases, options-dict).

PAGE_1 = {
    "layout_name": "IE Household",
    "layout_size": "4.5m",
    "page": 1,
    "total_pages": 2,
    "bays": [
        {
            "shelves": [
                (33, 62, 0, [
                    ("7182265", "Black Diffuser SK1", 2),
                    ("237582", "White Diffuser SK2", 2),
                    ("7138709", "Day Spa Diffuser", 2),
                    ("7127926", "Vintage Floral Diffuser", 3),
                    ("5231121", "Ceremony Of Scent Diffuser", 3),
                ]),
                (26, 62, 0, [
                    ("5236715", "Black Candle Candles SK2", 4),
                    ("5236708", "White Candles SK2", 4),
                    ("1003553", "Scented Candles 32h", 2),
                    ("5236701", "CeremonyOf Scent Candles", 4),
                ]),
                (20, 62, 0, [
                    ("7126601", "Everyday Jar Candle SK4", 2),
                    ("5723287", "Scented Glass Candle SK", 4),
                    ("1003764", "White Tealights", 3),
                ]),
                (13, 62, 0, [
                    ("65810", "Air Freshener 150ml", 2),
                    ("233114", "Plug in Air Freshener SK1", 2),
                    ("7001068", "Plug in Refill", 4),
                    ("1005171", "Dinner Candles", 2),
                ]),
                (3, 80, 0, [
                    ("213137", "Gel Air Freshener SK6", 6),
                    ("217968", "Air Freshener SK6", 6),
                    ("240392", "Air Diffuser Cotton/Lavender", 4),
                    ("1060", "Febreze Bathroom Spring Awakening", 3, {"tiny": True}),
                    ("7137122", "Febreze Air Freshener Spray Cotton", 3, {"tiny": True}),
                ]),
            ],
        },
        {
            "shelves": [
                (33, 62, 0, [
                    ("266326", "Biodegradable Floor Wipes", 4),
                    ("7005368", "Biodegradable Antibacterial Wipes", 8),
                ]),
                (2, 80, 0, [
                    ("230167", "Thick Bleach Original/Citrus", 2),
                ]),
                (3, 80, 0, [
                    ("209302", "Thick Bleach Original/Citrus", 1),
                ]),
            ],
        },
        {
            "shelves": [
                (33, 62, 0, [
                    ("7008058", "Flash Bleach Cleaning Spray 800ml", 2),
                    ("7008057", "Flash Kitchen Cleaning Spray 800Ml", 2),
                    ("7008059", "Flash Bathroom Cleaning Spray 800Ml", 2),
                    ("7022077", "Dettol Antibac Trigger", 4),
                ]),
                (19, 62, 0, [
                    ("7012188", "All Purpose Spray With Bleach", 4),
                    ("211746", "Antibacterial Multi-Action Cleaner", 8),
                    ("210846", "Kitchen Cleaner", 4),
                    ("211642", "Cleaning Spray Bathroom/Shower", 4),
                    ("224424", "Cleaner Limescale/Degreaser", 4),
                ]),
                (11, 62, 0, [
                    ("7012611", "Toilet Blocks WK9", 8),
                    ("227481", "Toilet Rim Blocks", 2),
                    ("200800", "Liquid Toilet Blocks", 2),
                    ("250592", "Toilet Gel with applicator", 4),
                ]),
                (3, 80, 0, [
                    ("234787", "Domestos Bleach", 4),
                    ("250153", "Sink &Drain Cleaner", 6),
                    ("241390", "Cream Cleaner", 4),
                    ("241709", "Toilet Cleaner", 4),
                    ("209041", "All Purpose Cleaner", 2),
                ]),
            ],
            "marker": "NTA",
        },
    ],
}

PAGE_2 = {
    "layout_name": "IE Household",
    "layout_size": "4.5m",
    "page": 2,
    "total_pages": 2,
    # Bays 2 and 3 carry no notch lines of their own: they share bay 1's shelves.
    "bays": [
        {
            "shelves": [
                (33, 62, 0, [
                    ("250810", "The Pink Stuff Miracle Paste", 2),
                    ("217970", "Furniture Polish Beeswax Multi", 2),
                ]),
                (22, 62, 0, [
                    ("7002958", "Washing Up Liquid", 8),
                ]),
                (12, 62, 0, [
                    ("7008038", "Fairy 654ml Original", 4),
                    ("1023107", "Fairy WUL Lemon", 2),
                    ("7190489", "Fairy WUL Pomegranate& Grapefruit", 2),
                    ("10076121", "Fairy Max Power 730ml", 2),
                ]),
                (3, 80, 0, [
                    ("10176277", "Other All Purpose Lemon 2L", 2),
                    ("247085", "Washing up liquid bigsize", 6),
                    ("7145365", "Washingup liquid 1.5L", 3),
                    ("261910", "Dishwashing Liquid Refill", 3),
                    ("241466", "Dishwasher Rinse Aid Energy", 4),
                ]),
            ],
            "marker": "NTA",
        },
        {
            "share_shelves_with_previous_bay": True,
            "shelves": [
                (33, 62, 0, [
                    ("202946", "Carpet& Upholstery Foam Cleaner", 2),
                    ("213350", "Platinum Dishwasher Tabs 40WL", 4),
                ]),
                (22, 62, 0, [
                    ("7006174", "WashingUp Liquid Antibacterial", 4),
                    ("151529", "Platinum Washing up Liquid", 4),
                ]),
                (12, 62, 0, [
                    ("200593", "Dishwasher Salt", 4),
                    ("204356", "Dishwasher Cleaner", 8),
                ]),
                (3, 80, 0, []),
            ],
        },
        {
            "share_shelves_with_previous_bay": True,
            "shelves": [
                (33, 62, 0, [
                    ("7175141", "All-in-1 Dishwasher Tabs 60WL", 8),
                    ("7149115", "All-in-1 Dishwasher Tabs Lemon 60WL", 8),
                    ("10007181", "Dishwasher Tablets Family Pack 80WL", 4),
                    ("5481", "Finish Quantum Ultimate", 2),
                ]),
                (22, 62, 0, []),
                (12, 62, 0, []),
                (3, 80, 0, []),
            ],
        },
    ],
}

PAGES = [PAGE_1, PAGE_2]

HEADER_CONTACT = "Contact layoutmanagement@lidl.ie with any queries/suggestions"
FOOTER_NOTE = (
    "Ambient Layouts: First visible notch above the plinth is notch 4. "
    "Chiller Layouts: First visible notch above the base is notch 1"
)
