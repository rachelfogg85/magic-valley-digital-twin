"""Tool functions shared by the agent (agent.py) and the Flask /api/optimize route
(server/app.py), so the plan shown on the map and the plan the agent describes in
words are always computed by the exact same code.
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "optimizer"))
from lp import solve  # noqa: E402

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
FIELDS = [
    {"field_id": r.field_id, "acres": r.acres}
    for r in gpd.read_file(DATA_DIR / "fields.geojson").itertuples()
]
_FIELDS_BY_ID = {f["field_id"]: f for f in FIELDS}

CROP_PARAMS = {
    # keep_default_na=False: pandas otherwise silently reads strings like "n/a" or
    # "null" as NaN in ANY column (not just numeric ones) -- bit us once already.
    row["crop"]: row.to_dict()
    for _, row in pd.read_csv(DATA_DIR / "crop_params.csv", keep_default_na=False).iterrows()
}

_water_baseline = pd.read_csv(DATA_DIR / "water_baseline.csv").set_index("scenario")["water_af"]
NORMAL_WATER_AF = float(_water_baseline["normal_year"])

_history_df = pd.read_csv(DATA_DIR / "field_history.csv")
HISTORY = {}
for _, row in _history_df.iterrows():
    HISTORY.setdefault(row["field_id"], {})[int(row["year"])] = row["crop_name"]

ACREAGE_CAPS = {
    "Sugar Beets": CONFIG["contracts"]["sugar_beet_acreage_cap"],
    "Potatoes": CONFIG["contracts"]["potato_acreage_cap"],
}

# Every number the agent states must be traceable to one of these. Returned with
# every tool result so the agent can cite a real source instead of a vague one.
DATA_SOURCES = {
    "prices": "Idaho State Tax Commission, average prices received by crop, 2018-2022",
    "yields": "USDA NASS, Idaho state average yields, 2023",
    "costs_per_acre": "Representative South-Central Idaho enterprise-budget magnitudes "
    "(see crop_params.csv 'source' column per crop; UI Extension's own budget PDFs "
    "were not machine-accessible when this was built -- treat as approximate)",
    "water_use_per_acre": "Kimberly, ID AgriMet station, 30-year average seasonal ET "
    "(University of Idaho Extension, Elmore County)",
    "drought_2021_cut": "Twin Falls Canal Company 2021 delivery cut (3/4in to 1/2in per "
    "share), per local news coverage (KMVT/KIVI)",
    "crop_history": "USDA Cropland Data Layer (CDL) 2008-2021, via Microsoft Planetary "
    "Computer's usda-cdl collection",
    "field_boundaries": "Generated from CDL pixels, not surveyed -- see this repo's "
    "output/design.md for the known limitation (adjacent same-crop fields can merge)",
    "terrain": "USGS 3DEP 1/3 arc-second DEM",
}


def _plan_profit_at(plan, price_case):
    total = 0.0
    for field_id, crop in plan.items():
        p = CROP_PARAMS[crop]
        profit_per_acre = p[f"price_{price_case}"] * p[f"yield_{price_case}"] - p["cost_per_acre"]
        total += _FIELDS_BY_ID[field_id]["acres"] * profit_per_acre
    return round(total, 2)


def _actual_plan_for_year(year):
    plan, acres_by_crop = {}, {}
    for f in FIELDS:
        crop = HISTORY.get(f["field_id"], {}).get(year)
        if crop is None or crop not in CROP_PARAMS:
            continue
        plan[f["field_id"]] = crop
        acres_by_crop[crop] = acres_by_crop.get(crop, 0) + f["acres"]
    return plan, {c: round(a, 1) for c, a in acres_by_crop.items()}


YEAR_RANGE = (CONFIG["years"]["start"], CONFIG["years"]["end"])


def run_optimizer(water_pct, year, price_case="mid"):
    if not (YEAR_RANGE[0] <= year <= YEAR_RANGE[1]):
        return {
            "error": f"No data for year {year}. This study area's real crop-history and "
            f"rotation data only covers {YEAR_RANGE[0]}-{YEAR_RANGE[1]}. Ask the user which "
            f"year in that range they mean, or use {CONFIG['drought_year']} (the drought year "
            "this project centers on) if they don't have one in mind."
        }
    water_limit_af = NORMAL_WATER_AF * (water_pct / 100.0)
    result = solve(
        FIELDS, CROP_PARAMS, water_limit_af,
        year=year, price_case=price_case, use_rotation=True,
        history=HISTORY, acreage_caps=ACREAGE_CAPS,
    )
    result["profit_low"] = _plan_profit_at(result["plan"], "low")
    result["profit_mid"] = _plan_profit_at(result["plan"], "mid")
    result["profit_high"] = _plan_profit_at(result["plan"], "high")
    result["water_limit_af"] = round(water_limit_af, 1)

    actual_plan, actual_acres_by_crop = _actual_plan_for_year(year)
    result["actual_acres_by_crop"] = actual_acres_by_crop
    result["actual_profit_low"] = _plan_profit_at(actual_plan, "low") if actual_plan else None
    result["actual_profit_mid"] = _plan_profit_at(actual_plan, "mid") if actual_plan else None
    result["actual_profit_high"] = _plan_profit_at(actual_plan, "high") if actual_plan else None
    result["units"] = {c: CROP_PARAMS[c]["unit"] for c in result["acres_by_crop"]}
    result["sources"] = {
        k: DATA_SOURCES[k]
        for k in ("prices", "yields", "costs_per_acre", "water_use_per_acre", "field_boundaries")
    }
    if year == CONFIG.get("drought_year"):
        result["sources"]["drought_2021_cut"] = DATA_SOURCES["drought_2021_cut"]
    return result


def get_field_history(field_id):
    hist = HISTORY.get(field_id)
    if hist is None:
        return {"error": f"No field with id {field_id!r}."}
    field = _FIELDS_BY_ID.get(field_id, {})
    return {
        "field_id": field_id,
        "acres": field.get("acres"),
        "history": {str(y): crop for y, crop in sorted(hist.items())},
        "source": DATA_SOURCES["crop_history"],
    }


def compare_to_actual(water_pct, year):
    result = run_optimizer(water_pct, year)
    if "error" in result:
        return result
    return {
        "year": year,
        "water_pct": water_pct,
        "optimized_profit_mid": result["profit_mid"],
        "optimized_acres_by_crop": result["acres_by_crop"],
        "actual_profit_mid": result["actual_profit_mid"],
        "actual_acres_by_crop": result["actual_acres_by_crop"],
        "profit_gap_mid": (
            round(result["profit_mid"] - result["actual_profit_mid"], 2)
            if result["actual_profit_mid"] is not None
            else None
        ),
        "sources": result["sources"],
    }
