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
    row["crop"]: row.to_dict() for _, row in pd.read_csv(DATA_DIR / "crop_params.csv").iterrows()
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


def run_optimizer(water_pct, year, price_case="mid"):
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
    result["actual_profit_mid"] = _plan_profit_at(actual_plan, "mid") if actual_plan else None
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
    }


def compare_to_actual(water_pct, year):
    result = run_optimizer(water_pct, year)
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
    }
