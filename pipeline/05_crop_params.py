"""Build crop_params.csv and water_baseline.csv from researched public data.

Covers the 7 crops that actually matter in our study area (by acreage in
field_history.csv) plus Fallow, matching the build plan's original list almost
exactly: corn, alfalfa, wheat, barley, potatoes, sugar beets, dry beans.

Data sources (see the `source` column in crop_params.csv for the per-row detail):
- Prices: Idaho State Tax Commission's 5-year (2018-2022) average-price-received
  table (low/mid/high = min/average/max of those 5 years).
- Yields: USDA NASS Idaho 2023 state averages where available.
- Water use: Kimberly, ID AgriMet station 30-year average seasonal ET (University of
  Idaho Extension, Elmore County).
- Costs per acre: representative South-Central Idaho enterprise-budget magnitudes.
  The actual University of Idaho AgBiz budget PDFs/spreadsheets for this region
  (Southcentral Idaho: corn, alfalfa, barley, dry beans, potatoes, sugarbeets, wheat)
  returned 403/zip downloads to automated fetching on 2026-10-22, so these are
  informed approximations, not a direct read of those documents. Flagged in the
  report as a number to double-check by hand, per the build plan's own guidance.

Water_baseline.csv: "normal" demand is this area's own average historical water use
(field acreage x crop water rate, averaged over 2008-2020), and the drought-year
demand applies Twin Falls Canal Company's documented 2021 cut -- deliveries fell from
3/4 inch to 1/2 inch per share, about a 33% reduction -- to that baseline.
"""
import csv
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"

CROPS = [
    {
        "crop": "Corn", "unit": "bu",
        "price_low": 4.42, "price_mid": 5.42, "price_high": 7.37,
        "yield_low": 175, "yield_mid": 204, "yield_high": 230,
        "cost_per_acre": 850, "water_af_per_acre": 2.25,
        "source": (
            "Price: Idaho State Tax Commission avg prices received, 2018-2022 "
            "(min/avg/max of 5 years). Yield: USDA NASS Idaho 2023 state avg "
            "(204 bu/ac); low/high are +-~13% since no historical percentile data "
            "was accessible in the time available. Cost: representative "
            "South-Central Idaho irrigated field corn budget magnitude "
            "(approximate -- UI Extension AgBiz budget files were not machine- "
            "accessible). Water: Kimberly AgriMet 30-yr seasonal ET."
        ),
    },
    {
        "crop": "Alfalfa", "unit": "ton",
        "price_low": 152, "price_mid": 190.40, "price_high": 272,
        "yield_low": 3.8, "yield_mid": 4.4, "yield_high": 5.0,
        "cost_per_acre": 550, "water_af_per_acre": 3.4,
        "source": (
            "Price: Idaho State Tax Commission avg prices received, 2018-2022. "
            "Yield: USDA NASS Idaho 2023 state avg (4.4 ton/ac); low/high "
            "approximate. Cost: representative established alfalfa-hay production "
            "budget magnitude (approximate). Water: Kimberly AgriMet 30-yr ET."
        ),
    },
    {
        "crop": "Wheat (winter)", "unit": "bu",
        "price_low": 5.08, "price_mid": 6.16, "price_high": 8.20,
        "yield_low": 75, "yield_mid": 87, "yield_high": 100,
        "cost_per_acre": 430, "water_af_per_acre": 1.9,
        "source": (
            "Price: Idaho spring-wheat avg prices 2018-2022 used as a close proxy "
            "(2022 winter wheat was $7.97 vs spring $8.20, tracking closely). "
            "Yield: approximate Idaho state average. Cost: representative "
            "South-Central Idaho winter wheat budget magnitude (approximate). "
            "Water: Kimberly AgriMet winter-grain seasonal ET."
        ),
    },
    {
        "crop": "Wheat (spring)", "unit": "bu",
        "price_low": 5.08, "price_mid": 6.16, "price_high": 8.20,
        "yield_low": 70, "yield_mid": 82, "yield_high": 95,
        "cost_per_acre": 420, "water_af_per_acre": 1.8,
        "source": (
            "Price: Idaho State Tax Commission avg prices received, 2018-2022. "
            "Yield: approximate, slightly below winter wheat (shorter season). "
            "Cost: representative budget magnitude (approximate). Water: approx., "
            "slightly below winter grain (Kimberly AgriMet)."
        ),
    },
    {
        "crop": "Barley", "unit": "bu",
        "price_low": 3.27, "price_mid": 4.30, "price_high": 6.15,
        "yield_low": 95, "yield_mid": 110, "yield_high": 125,
        "cost_per_acre": 400, "water_af_per_acre": 1.7,
        "source": (
            "Price: Idaho feed-barley avg prices received, 2018-2022. Yield: "
            "approximate Magic Valley irrigated average. Cost: representative "
            "feed-barley budget magnitude (approximate). Water: approximate, "
            "similar to spring grain (Kimberly AgriMet)."
        ),
    },
    {
        "crop": "Potatoes", "unit": "cwt",
        "price_low": 7.25, "price_mid": 8.69, "price_high": 12.50,
        "yield_low": 380, "yield_mid": 440, "yield_high": 480,
        "cost_per_acre": 3500, "water_af_per_acre": 2.0,
        "source": (
            "Price: Idaho State Tax Commission avg prices received, 2018-2022. "
            "Yield: USDA NASS Idaho 2023 state avg (440 cwt/ac). Cost: "
            "representative Russet Burbank storage/fumigation budget magnitude "
            "(approximate -- potatoes are by far the most input-intensive crop "
            "here). Water: Kimberly AgriMet 30-yr ET."
        ),
    },
    {
        "crop": "Sugar Beets", "unit": "ton",
        "price_low": 46.00, "price_mid": 52.60, "price_high": 60.00,
        "yield_low": 34, "yield_mid": 39.4, "yield_high": 43,
        "cost_per_acre": 1700, "water_af_per_acre": 2.6,
        "source": (
            "Price: Idaho State Tax Commission avg prices received, 2018-2021 "
            "(2022 not reported). Yield: USDA NASS Idaho 2023 forecast "
            "(39.4 ton/ac). Cost: representative Roundup Ready sugarbeet budget "
            "magnitude (approximate). Water: approximate, long-season high-water "
            "crop, above corn and below alfalfa."
        ),
    },
    {
        "crop": "Beans", "unit": "cwt",
        "price_low": 23.50, "price_mid": 32.32, "price_high": 43.90,
        "yield_low": 20, "yield_mid": 24.7, "yield_high": 28,
        "cost_per_acre": 525, "water_af_per_acre": 1.5,
        "source": (
            "Price: Idaho dry-bean avg prices received, 2018-2022. Yield: USDA "
            "NASS Idaho 2023 state avg (24.7 cwt/ac). Cost: representative dry "
            "bean budget magnitude (approximate). Water: approximate, shortest- "
            "season crop in this set."
        ),
    },
    {
        "crop": "Fallow", "unit": "n/a",
        "price_low": 0, "price_mid": 0, "price_high": 0,
        "yield_low": 0, "yield_mid": 0, "yield_high": 0,
        "cost_per_acre": 0, "water_af_per_acre": 0,
        "source": "No crop grown: zero revenue, zero cost, zero water use, by definition.",
    },
]

DROUGHT_CUT_FRACTION = 0.33  # Twin Falls Canal Co. cut 2021 deliveries from 3/4" to
                              # 1/2" per share -- about a one-third reduction.
DROUGHT_SOURCE = (
    "Twin Falls Canal Company reduced 2021 per-share deliveries from 3/4 inch to "
    "1/2 inch (and briefly 5/8 inch) due to drought -- roughly a 33% cut from a "
    "normal year, per local news coverage (KMVT/KIVI/Magic Valley Canal reporting)."
)


def write_crop_params():
    path = PROCESSED_DIR / "crop_params.csv"
    fieldnames = [
        "crop", "unit", "price_low", "price_mid", "price_high",
        "yield_low", "yield_mid", "yield_high", "cost_per_acre",
        "water_af_per_acre", "source",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(CROPS)
    print(f"Saved {path.relative_to(ROOT)} ({len(CROPS)} crops)")


def write_water_baseline():
    history = pd.read_csv(PROCESSED_DIR / "field_history.csv")
    params = pd.DataFrame(CROPS)[["crop", "water_af_per_acre"]]

    normal_years = history[history["year"] != 2021]
    merged = normal_years.merge(params, left_on="crop_name", right_on="crop", how="left")
    merged["water_af_per_acre"] = merged["water_af_per_acre"].fillna(0)
    merged["field_water_af"] = merged["acres"] * merged["water_af_per_acre"]

    per_year_af = merged.groupby("year")["field_water_af"].sum()
    normal_year_af = round(float(per_year_af.mean()), 1)
    drought_year_af = round(normal_year_af * (1 - DROUGHT_CUT_FRACTION), 1)

    path = PROCESSED_DIR / "water_baseline.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario", "water_af", "source"])
        writer.writerow([
            "normal_year", normal_year_af,
            "Average implied water demand (field acres x crop_params water rate) "
            "across this study area's own 2008-2020 crop history (2021 excluded).",
        ])
        writer.writerow(["drought_year_2021", drought_year_af, DROUGHT_SOURCE])
    print(f"Saved {path.relative_to(ROOT)}: normal={normal_year_af} AF, drought_2021={drought_year_af} AF "
          f"({int(DROUGHT_CUT_FRACTION * 100)}% cut)")


def main():
    write_crop_params()
    write_water_baseline()


if __name__ == "__main__":
    main()
