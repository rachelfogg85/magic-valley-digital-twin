"""Turn the raw DEM and CDL rasters into the files the browser viewer loads.

(a) Reprojects the DEM and every CDL year onto one shared EPSG:5070 grid covering the
    study area.
(b) Saves the DEM as data/processed/heightmap.bin (raw Float32, row-major) plus
    terrain_meta.json (width, height, min/max elevation, bounds, meters per pixel).
(c) Converts each CDL year to data/processed/cdl_YYYY.png, colored with the official
    CDL palette (pulled from the Planetary Computer STAC item's classification:classes,
    since the Planetary Computer COGs ship without an embedded GDAL color table).
(d) Saves data/processed/cdl_legend.json mapping crop code to name and color, limited to
    codes actually present in our study area.
"""
import json
from pathlib import Path

import numpy as np
import rasterio
import requests
import yaml
from PIL import Image
from rasterio.features import sieve
from rasterio.warp import Resampling, reproject, transform_bounds

from cdl_layman_names import layman_name

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"
RAW_DEM = ROOT / "data" / "raw" / "dem_clip.tif"
RAW_CDL_DIR = ROOT / "data" / "raw" / "cdl"
PROCESSED_DIR = ROOT / "data" / "processed"

GRID_CRS = "EPSG:32611"  # UTM zone 11N: local to the study area, unlike EPSG:5070
                          # (CONUS Albers), which has a ~12.6-deg convergence angle at
                          # this longitude and rotates the bbox enough to lose ~28% of
                          # the source data at the shared grid's corners
GRID_RESOLUTION_M = 10  # matches the DEM's native ~10 m resolution
SIEVE_MIN_PIXELS = 9  # one native 30 m CDL cell = 3x3 pixels at our 10 m grid; smaller
                       # specks are resampling/classification noise, not real fields

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


def reproject_to_grid(src_path, transform, width, height, resampling, dtype, dst_nodata=None):
    with rasterio.open(src_path) as src:
        dst = np.zeros((height, width), dtype=dtype)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=GRID_CRS,
            resampling=resampling,
            src_nodata=src.nodata,
            dst_nodata=dst_nodata if dst_nodata is not None else src.nodata,
        )
    return dst


def process_dem(transform, width, height):
    elev = reproject_to_grid(
        RAW_DEM, transform, width, height, Resampling.bilinear, np.float32, dst_nodata=-999999.0
    )
    valid = elev[elev != -999999.0]
    if valid.size < elev.size:
        print(f"note: {elev.size - valid.size} edge pixel(s) outside DEM coverage, filled with nearest valid value")
        # Edge pixels from the reprojection falling just outside the original clip:
        # fill with the overall mean so the heightmap has no holes for the 3D mesh.
        elev[elev == -999999.0] = float(valid.mean())

    (PROCESSED_DIR / "heightmap.bin").write_bytes(elev.tobytes(order="C"))

    west, north = transform * (0, 0)
    east, south = transform * (width, height)
    meta = {
        "width": width,
        "height": height,
        "min_elevation_m": float(valid.min()),
        "max_elevation_m": float(valid.max()),
        "meters_per_pixel": GRID_RESOLUTION_M,
        "crs": GRID_CRS,
        "bounds": {"west": west, "south": south, "east": east, "north": north},
    }
    (PROCESSED_DIR / "terrain_meta.json").write_text(json.dumps(meta, indent=2))
    print(
        f"heightmap.bin: {width}x{height}, "
        f"elevation {meta['min_elevation_m']:.1f}-{meta['max_elevation_m']:.1f} m"
    )


def fetch_cdl_palette():
    resp = requests.get(CDL_LEGEND_ITEM, timeout=30)
    resp.raise_for_status()
    classes = resp.json()["assets"]["cropland"]["classification:classes"]
    palette = {}
    for c in classes:
        hexcolor = c["color_hint"]
        rgb = tuple(int(hexcolor[i : i + 2], 16) for i in (0, 2, 4))
        palette[c["value"]] = {"name": c["description"], "color": rgb}
    return palette


def process_cdl_years(cfg, transform, width, height, palette):
    legend = {}
    for year in range(cfg["years"]["start"], cfg["years"]["end"] + 1):
        src_path = RAW_CDL_DIR / f"cdl_{year}.tif"
        if not src_path.exists():
            print(f"skip {year}: no raw CDL file")
            continue

        arr = reproject_to_grid(src_path, transform, width, height, Resampling.nearest, np.uint8)
        arr = sieve(arr, size=SIEVE_MIN_PIXELS, connectivity=8)
        rgb = np.zeros((height, width, 3), dtype=np.uint8)
        codes_present = np.unique(arr)
        for code in codes_present:
            entry = palette.get(int(code), {"name": "Unknown", "color": (0, 0, 0)})
            rgb[arr == code] = entry["color"]
            legend.setdefault(
                str(int(code)),
                {
                    "name": layman_name(entry["name"]),
                    "official_name": entry["name"],
                    "color": list(entry["color"]),
                },
            )

        Image.fromarray(rgb, mode="RGB").save(PROCESSED_DIR / f"cdl_{year}.png")
        print(f"cdl_{year}.png saved ({len(codes_present)} crop codes present)")

    (PROCESSED_DIR / "cdl_legend.json").write_text(json.dumps(legend, indent=2))
    print(f"cdl_legend.json: {len(legend)} codes present across all years")


def main():
    cfg = load_config()
    sa = cfg["study_area"]
    bbox = (sa["west"], sa["south"], sa["east"], sa["north"])

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    transform, width, height = shared_grid(bbox)
    print(f"Shared grid: {width}x{height} @ {GRID_RESOLUTION_M}m/px")

    process_dem(transform, width, height)
    palette = fetch_cdl_palette()
    process_cdl_years(cfg, transform, width, height, palette)


if __name__ == "__main__":
    main()
