"""Download the USDA Cropland Data Layer (CDL) for every year in config.yaml, clipped
to the study-area bounding box.

The original CropScape GetCDLFile web service (nassgeodata.gmu.edu) was unreliable when
tested (requests either timed out or returned a 502 proxy error), so this uses Microsoft
Planetary Computer's public, no-key mirror of the same USDA data instead: a STAC search
finds the "cropland" asset (a cloud-optimized GeoTIFF) covering our bbox for a given year,
a free anonymous token signs the URL, and a windowed read clips straight to our small box
without downloading the full CDL tile.
"""
from pathlib import Path

import numpy as np
import rasterio
import requests
import yaml
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"
RAW_CDL_DIR = ROOT / "data" / "raw" / "cdl"

STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/usda-cdl"


def load_config():
    return yaml.safe_load(CONFIG_PATH.read_text())


def get_token():
    return requests.get(SAS_TOKEN_URL, timeout=20).json()["token"]


def find_cropland_asset(bbox, year):
    params = {
        "collections": "usda-cdl",
        "bbox": ",".join(str(v) for v in bbox),
        "datetime": f"{year}-01-01/{year}-12-31",
        "limit": 20,
    }
    resp = requests.get(STAC_SEARCH, params=params, timeout=30)
    resp.raise_for_status()
    features = resp.json()["features"]
    for f in features:
        if f["id"].startswith("cropland_"):
            return f["assets"]["cropland"]["href"]
    raise RuntimeError(f"No cropland item found for {year} over bbox {bbox}")


def download_and_clip(year, bbox, token):
    href = find_cropland_asset(bbox, year)
    vsi_url = f"/vsicurl/{href}?{token}"
    west, south, east, north = bbox

    with rasterio.open(vsi_url) as src:
        cw, cs, ce, cn = transform_bounds("EPSG:4326", src.crs, west, south, east, north)
        window = from_bounds(cw, cs, ce, cn, src.transform)
        arr = src.read(1, window=window)
        win_transform = src.window_transform(window)
        profile = {
            "driver": "GTiff",
            "height": arr.shape[0],
            "width": arr.shape[1],
            "count": 1,
            "dtype": arr.dtype,
            "crs": src.crs,
            "transform": win_transform,
            "nodata": src.nodata,
        }

    dest = RAW_CDL_DIR / f"cdl_{year}.tif"
    with rasterio.open(dest, "w", **profile) as dst:
        dst.write(arr, 1)
    return dest, arr, profile["nodata"]


def top_crops(arr, nodata, n=5):
    vals, counts = np.unique(arr, return_counts=True)
    order = np.argsort(-counts)
    out = []
    for idx in order:
        v = vals[idx]
        if nodata is not None and v == nodata:
            continue
        out.append((int(v), int(counts[idx])))
        if len(out) == n:
            break
    return out


def main():
    cfg = load_config()
    sa = cfg["study_area"]
    bbox = (sa["west"], sa["south"], sa["east"], sa["north"])
    print(f"Study area bbox (WGS84): {bbox}")

    RAW_CDL_DIR.mkdir(parents=True, exist_ok=True)
    token = get_token()

    for year in range(cfg["years"]["start"], cfg["years"]["end"] + 1):
        dest = RAW_CDL_DIR / f"cdl_{year}.tif"
        if dest.exists():
            with rasterio.open(dest) as src:
                arr = src.read(1)
                nodata = src.nodata
            print(f"{year}: already downloaded")
        else:
            dest, arr, nodata = download_and_clip(year, bbox, token)
            print(f"{year}: downloaded and clipped -> {dest.relative_to(ROOT)}")

        print(f"{year} top 5 crop codes (code, pixel count): {top_crops(arr, nodata)}")


if __name__ == "__main__":
    main()
