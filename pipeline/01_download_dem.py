"""Download and clip the USGS 3DEP 1/3 arc-second DEM for the study area in config.yaml.

Uses the USGS National Map (TNM) Access API, which needs no key, to find the DEM
tile(s) covering the bounding box, downloads them into data/raw/dem/, mosaics them
if there is more than one, clips to the exact bounding box, and writes
data/raw/dem_clip.tif.
"""
from pathlib import Path

import numpy as np
import rasterio
import requests
import yaml
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"
RAW_DEM_DIR = ROOT / "data" / "raw" / "dem"
OUT_PATH = ROOT / "data" / "raw" / "dem_clip.tif"

TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"
DATASET = "National Elevation Dataset (NED) 1/3 arc-second"


def load_bbox():
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    sa = cfg["study_area"]
    return sa["west"], sa["south"], sa["east"], sa["north"]


def find_tiles(bbox):
    west, south, east, north = bbox
    params = {
        "datasets": DATASET,
        "bbox": f"{west},{south},{east},{north}",
        "prodFormats": "GeoTIFF",
    }
    resp = requests.get(TNM_API, params=params, timeout=60)
    resp.raise_for_status()
    items = resp.json()["items"]

    # Keep only real 1/3 arc-second tiles, newest publication per tile id.
    best = {}
    for item in items:
        title = item["title"]
        if "1/3 Arc Second" not in title:
            continue
        tile_id = title.split(" 20")[0]
        date = item.get("publicationDate", "")
        if tile_id not in best or date > best[tile_id]["publicationDate"]:
            best[tile_id] = item
    if not best:
        raise RuntimeError("No 1/3 arc-second DEM tiles found for this bounding box.")
    return list(best.values())


def download_tiles(tiles):
    RAW_DEM_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for item in tiles:
        url = item["downloadURL"]
        dest = RAW_DEM_DIR / Path(url).name
        if dest.exists():
            print(f"Already downloaded: {dest.name}")
        else:
            print(f"Downloading {url}")
            with requests.get(url, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
        paths.append(dest)
    return paths


def mosaic_and_clip(paths, bbox):
    west, south, east, north = bbox
    srcs = [rasterio.open(p) for p in paths]
    mosaic, transform = merge(srcs)
    crs = srcs[0].crs
    nodata = srcs[0].nodata
    for s in srcs:
        s.close()

    profile = {
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "count": 1,
        "dtype": mosaic.dtype,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
    }
    with MemoryFile() as memfile:
        with memfile.open(**profile) as mem:
            mem.write(mosaic)
            cw, cs, ce, cn = transform_bounds("EPSG:4326", crs, west, south, east, north)
            window = from_bounds(cw, cs, ce, cn, mem.transform)
            clipped = mem.read(1, window=window)
            clip_transform = mem.window_transform(window)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_profile = {
        "driver": "GTiff",
        "height": clipped.shape[0],
        "width": clipped.shape[1],
        "count": 1,
        "dtype": clipped.dtype,
        "crs": crs,
        "transform": clip_transform,
        "nodata": nodata,
    }
    with rasterio.open(OUT_PATH, "w", **out_profile) as dst:
        dst.write(clipped, 1)

    return clipped


def main():
    bbox = load_bbox()
    print(f"Study area bbox (WGS84): {bbox}")

    tiles = find_tiles(bbox)
    print(f"Found {len(tiles)} DEM tile(s): {[t['title'] for t in tiles]}")

    paths = download_tiles(tiles)
    clipped = mosaic_and_clip(paths, bbox)

    valid = clipped[clipped != -999999] if np.any(clipped == -999999) else clipped
    print(f"Clipped raster size: {clipped.shape[1]} x {clipped.shape[0]} (width x height)")
    print(f"Elevation min/max (m): {float(np.nanmin(valid)):.1f} / {float(np.nanmax(valid)):.1f}")
    print(f"Saved to {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
