"""Generate field boundary polygons automatically from the CDL raster.

The build plan's original Step 6 was to hand-trace 20-40 fields in QGIS/geojson.io,
but geojson.io was blocked for Rachel, so this does it algorithmically instead:
contiguous same-crop pixels in a reference year are grouped into polygons, with
non-agricultural land cover (development, water, forest, etc.) and tiny noise
polygons dropped. Writes data/processed/fields.geojson (field_id, acres, geometry).

Caveat, noted here and in the report: these boundaries follow crop-classification
regions for one year, not true property/pivot lines, so two real adjacent fields
planted with the same crop in the reference year merge into a single polygon. Good
enough for a student project; a real deployment would use traced parcel boundaries.
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import requests
import yaml
from rasterio.features import shapes, sieve
from rasterio.warp import Resampling, reproject, transform_bounds
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"
RAW_CDL_DIR = ROOT / "data" / "raw" / "cdl"
PROCESSED_DIR = ROOT / "data" / "processed"

GRID_CRS = "EPSG:32611"
GRID_RESOLUTION_M = 10
SIEVE_MIN_PIXELS = 16
MIN_FIELD_ACRES = 3.0
REFERENCE_YEAR = 2021  # the drought year this project centers on

CDL_LEGEND_ITEM = (
    "https://planetarycomputer.microsoft.com/api/stac/v1/collections/usda-cdl/items/"
    "cropland_2021_-1546095_2362575_90000"
)
NON_FIELD_NAME_KEYWORDS = (
    "Developed", "Forest", "Wetlands", "Water", "Barren", "Shrubland",
    "Ice/Snow", "Unknown",
)


def load_config():
    return yaml.safe_load(CONFIG_PATH.read_text())


def shared_grid(bbox):
    west, south, east, north = bbox
    gw, gs, ge, gn = transform_bounds("EPSG:4326", GRID_CRS, west, south, east, north)
    width = int(round((ge - gw) / GRID_RESOLUTION_M))
    height = int(round((gn - gs) / GRID_RESOLUTION_M))
    transform = rasterio.transform.from_origin(gw, gn, GRID_RESOLUTION_M, GRID_RESOLUTION_M)
    return transform, width, height


def reproject_to_grid(src_path, transform, width, height):
    with rasterio.open(src_path) as src:
        dst = np.zeros((height, width), dtype=np.uint8)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=GRID_CRS,
            resampling=Resampling.nearest,
            src_nodata=src.nodata,
            dst_nodata=src.nodata,
        )
    return dst


def fetch_cdl_names():
    resp = requests.get(CDL_LEGEND_ITEM, timeout=30)
    resp.raise_for_status()
    classes = resp.json()["assets"]["cropland"]["classification:classes"]
    return {c["value"]: c["description"] for c in classes}


def main():
    cfg = load_config()
    sa = cfg["study_area"]
    bbox = (sa["west"], sa["south"], sa["east"], sa["north"])
    transform, width, height = shared_grid(bbox)

    src_path = RAW_CDL_DIR / f"cdl_{REFERENCE_YEAR}.tif"
    arr = reproject_to_grid(src_path, transform, width, height)
    arr = sieve(arr, size=SIEVE_MIN_PIXELS, connectivity=8)

    names = fetch_cdl_names()
    exclude_codes = {0} | {
        code for code, name in names.items() if any(k in name for k in NON_FIELD_NAME_KEYWORDS)
    }
    mask = ~np.isin(arr, list(exclude_codes))

    records = []
    for geom, value in shapes(arr, mask=mask, transform=transform, connectivity=8):
        value = int(value)
        poly = shape(geom)
        acres = poly.area / 4046.8564224
        if acres < MIN_FIELD_ACRES:
            continue
        records.append(
            {
                "geometry": poly,
                "crop_code_ref_year": value,
                "crop_name_ref_year": names.get(value, "Unknown"),
                "acres": round(acres, 1),
            }
        )

    gdf = gpd.GeoDataFrame(records, crs=GRID_CRS)
    gdf = gdf.sort_values("acres", ascending=False).reset_index(drop=True)
    gdf.insert(0, "field_id", [f"F{i + 1:02d}" for i in range(len(gdf))])
    gdf = gdf.to_crs("EPSG:4326")

    out_path = PROCESSED_DIR / "fields.geojson"
    gdf.to_file(out_path, driver="GeoJSON")

    print(f"Generated {len(gdf)} fields from {REFERENCE_YEAR} CDL (min {MIN_FIELD_ACRES} acres)")
    print(f"Total acreage: {gdf['acres'].sum():.1f}")
    print(f"Saved to {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
