"""Build each field's crop history: for every field (fields.geojson) and every year,
find the majority CDL crop code inside the polygon (zonal majority) and the share of
pixels it covers, plus the field's area in acres. Saves data/processed/field_history.csv
with columns field_id, acres, year, crop_code, crop_name, majority_share.
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
import yaml
from rasterio.features import rasterize, sieve
from rasterio.warp import Resampling, reproject, transform_bounds

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"
RAW_CDL_DIR = ROOT / "data" / "raw" / "cdl"
PROCESSED_DIR = ROOT / "data" / "processed"
FIELDS_PATH = PROCESSED_DIR / "fields.geojson"

GRID_CRS = "EPSG:32611"
GRID_RESOLUTION_M = 10
SIEVE_MIN_PIXELS = 16

CDL_LEGEND_ITEM = (
    "https://planetarycomputer.microsoft.com/api/stac/v1/collections/usda-cdl/items/"
    "cropland_2021_-1546095_2362575_90000"
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


def reproject_cdl(src_path, transform, width, height):
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
    return sieve(dst, size=SIEVE_MIN_PIXELS, connectivity=8)


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

    fields = gpd.read_file(FIELDS_PATH).to_crs(GRID_CRS)
    fields["acres"] = fields.geometry.area / 4046.8564224

    # Rasterize all fields at once: each pixel gets the row-index of the field it
    # falls in (0..n-1), or -1 if outside every field.
    shapes_in = list(zip(fields.geometry, range(len(fields))))
    zone_raster = rasterize(
        shapes_in, out_shape=(height, width), transform=transform, fill=-1, dtype="int32"
    )

    names = fetch_cdl_names()
    rows = []
    for year in range(cfg["years"]["start"], cfg["years"]["end"] + 1):
        src_path = RAW_CDL_DIR / f"cdl_{year}.tif"
        if not src_path.exists():
            print(f"{year}: skip, no raw CDL file")
            continue
        arr = reproject_cdl(src_path, transform, width, height)

        for i, field in fields.iterrows():
            field_pixels = arr[zone_raster == i]
            if field_pixels.size == 0:
                continue
            vals, counts = np.unique(field_pixels, return_counts=True)
            top = np.argmax(counts)
            crop_code = int(vals[top])
            majority_share = counts[top] / field_pixels.size
            rows.append(
                {
                    "field_id": field["field_id"],
                    "acres": round(field["acres"], 1),
                    "year": year,
                    "crop_code": crop_code,
                    "crop_name": names.get(crop_code, "Unknown"),
                    "majority_share": round(float(majority_share), 3),
                }
            )
        print(f"{year}: done")

    df = pd.DataFrame(rows)
    out_path = PROCESSED_DIR / "field_history.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows ({fields.shape[0]} fields x up to {cfg['years']['end'] - cfg['years']['start'] + 1} years) to {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
