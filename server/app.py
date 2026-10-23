"""Flask server: serves the web/ frontend, data/processed/ data files, and
POST /api/optimize (the scenario tool -- "N% less water, what do I plant?").
"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / "data" / "processed"

sys.path.insert(0, str(ROOT / "optimizer"))
from lp import solve  # noqa: E402

app = Flask(__name__, static_folder=None)

# Loaded once at startup; small enough (a few hundred KB total) to keep in memory.
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
FIELDS = [
    {"field_id": r.field_id, "acres": r.acres}
    for r in gpd.read_file(DATA_DIR / "fields.geojson").itertuples()
]
CROP_PARAMS = {
    row["crop"]: row.to_dict() for _, row in pd.read_csv(DATA_DIR / "crop_params.csv").iterrows()
}
WATER_BASELINE = pd.read_csv(DATA_DIR / "water_baseline.csv").set_index("scenario")["water_af"]
NORMAL_WATER_AF = float(WATER_BASELINE["normal_year"])

_history_df = pd.read_csv(DATA_DIR / "field_history.csv")
HISTORY = {}
for _, row in _history_df.iterrows():
    HISTORY.setdefault(row["field_id"], {})[int(row["year"])] = row["crop_name"]

ACREAGE_CAPS = {
    "Sugar Beets": CONFIG["contracts"]["sugar_beet_acreage_cap"],
    "Potatoes": CONFIG["contracts"]["potato_acreage_cap"],
}


def plan_profit_at(plan, price_case):
    total = 0.0
    acres_by_field = {f["field_id"]: f["acres"] for f in FIELDS}
    for field_id, crop in plan.items():
        p = CROP_PARAMS[crop]
        profit_per_acre = p[f"price_{price_case}"] * p[f"yield_{price_case}"] - p["cost_per_acre"]
        total += acres_by_field[field_id] * profit_per_acre
    return round(total, 2)


def actual_plan_for_year(year):
    plan, acres_by_crop = {}, {}
    for f in FIELDS:
        crop = HISTORY.get(f["field_id"], {}).get(year)
        if crop is None or crop not in CROP_PARAMS:
            continue
        plan[f["field_id"]] = crop
        acres_by_crop[crop] = acres_by_crop.get(crop, 0) + f["acres"]
    return plan, {c: round(a, 1) for c, a in acres_by_crop.items()}


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    body = request.get_json(force=True) or {}
    water_pct = float(body.get("water_pct", 100))
    year = int(body.get("year", 2021))
    price_case = body.get("price_case", "mid")
    use_rotation = bool(body.get("use_rotation", True))

    water_limit_af = NORMAL_WATER_AF * (water_pct / 100.0)

    result = solve(
        FIELDS, CROP_PARAMS, water_limit_af,
        year=year, price_case=price_case, use_rotation=use_rotation,
        history=HISTORY, acreage_caps=ACREAGE_CAPS,
    )
    result["profit_low"] = plan_profit_at(result["plan"], "low")
    result["profit_mid"] = plan_profit_at(result["plan"], "mid")
    result["profit_high"] = plan_profit_at(result["plan"], "high")
    result["water_limit_af"] = round(water_limit_af, 1)

    actual_plan, actual_acres_by_crop = actual_plan_for_year(year)
    result["actual_acres_by_crop"] = actual_acres_by_crop
    result["actual_profit_mid"] = plan_profit_at(actual_plan, "mid") if actual_plan else None

    return jsonify(result)


@app.route("/data/<path:path>")
def data_files(path):
    return send_from_directory(DATA_DIR, path)


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def web_files(path):
    return send_from_directory(WEB_DIR, path)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
