"""Plain-language display names for USDA CDL crop codes.

The official CDL class names are GIS/dataset jargon in places (e.g. "Developed/High
Intensity", "Dbl Crop" variants). This maps them to names a non-farmer reading the
report or demo can understand at a glance. Keyed by the official CDL name.
"""

LAYMAN_NAMES = {
    "Barley/Corn": "Barley then Corn (double crop)",
    "Barren": "Bare Ground",
    "Developed/High Intensity": "City / Dense Buildings",
    "Developed/Low Intensity": "Houses (scattered)",
    "Developed/Med Intensity": "Houses / Buildings",
    "Developed/Open Space": "Roads / Yards",
    "Dry Beans": "Beans",
    "Fallow/Idle Cropland": "Unplanted Field (resting)",
    "Grassland/Pasture": "Pasture / Grazing Land",
    "Herbaceous Wetlands": "Wetland (marsh)",
    "Open Water": "Water",
    "Other Hay/Non Alfalfa": "Hay (non-alfalfa)",
    "Other Small Grains": "Other Grains",
    "Perennial Ice/Snow": "Ice / Snow",
    "Shrubland": "Shrubs / Brush",
    "Sod/Grass Seed": "Lawn Sod / Grass Seed",
    "Spring Wheat": "Wheat (spring)",
    "Sugarbeets": "Sugar Beets",
    "Triticale": "Triticale (wheat-rye grain)",
    "Triticale/Corn": "Triticale then Corn (double crop)",
    "Unknown": "No Data",
    "Winter Wheat": "Wheat (winter)",
    "Winter Wheat/Corn": "Wheat then Corn (double crop)",
    "Woody Wetlands": "Wetland (trees)",
}


def layman_name(official_name: str) -> str:
    return LAYMAN_NAMES.get(official_name, official_name)
