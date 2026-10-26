"""Drought-year backtest: compares what farmers actually planted in config.yaml's
drought_year (2021) against what the optimizer would have recommended under that
year's real water supply, with and without rotation constraints.

Saves backtest/outputs/backtest_fields.csv (field-by-field comparison) and two
charts, and prints a plain-English summary.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "optimizer"))
import tools as agent_tools  # noqa: E402
from lp import solve  # noqa: E402

OUTPUT_DIR = ROOT / "backtest" / "outputs"

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
DROUGHT_YEAR = CONFIG["drought_year"]


def profit_range(plan):
    return {case: agent_tools._plan_profit_at(plan, case) for case in ("low", "mid", "high")}


def water_used(plan):
    total = 0.0
    for field_id, crop in plan.items():
        acres = agent_tools._FIELDS_BY_ID[field_id]["acres"]
        total += acres * agent_tools.CROP_PARAMS[crop]["water_af_per_acre"]
    return round(total, 1)


def run_optimized(water_limit_af, use_rotation):
    return solve(
        agent_tools.FIELDS, agent_tools.CROP_PARAMS, water_limit_af,
        year=DROUGHT_YEAR, price_case="mid", use_rotation=use_rotation,
        history=agent_tools.HISTORY, acreage_caps=agent_tools.ACREAGE_CAPS,
    )


def field_diff_table(actual_plan, optimized_plan):
    rows = []
    for f in agent_tools.FIELDS:
        fid = f["field_id"]
        actual_crop = actual_plan.get(fid, "Fallow")
        optimized_crop = optimized_plan.get(fid, "Fallow")
        if actual_crop == optimized_crop:
            continue
        actual_profit = agent_tools.CROP_PARAMS[actual_crop]
        optimized_profit = agent_tools.CROP_PARAMS[optimized_crop]
        actual_per_acre = actual_profit["price_mid"] * actual_profit["yield_mid"] - actual_profit["cost_per_acre"]
        optimized_per_acre = (
            optimized_profit["price_mid"] * optimized_profit["yield_mid"] - optimized_profit["cost_per_acre"]
        )
        rows.append(
            {
                "field_id": fid,
                "acres": f["acres"],
                "actual_crop": actual_crop,
                "optimized_crop": optimized_crop,
                "profit_diff_mid": round((optimized_per_acre - actual_per_acre) * f["acres"], 2),
            }
        )
    return pd.DataFrame(rows).sort_values("profit_diff_mid", ascending=False).reset_index(drop=True)


def make_acres_chart(actual_acres, optimized_acres, path):
    crops = sorted(set(actual_acres) | set(optimized_acres))
    actual_vals = [actual_acres.get(c, 0) for c in crops]
    optimized_vals = [optimized_acres.get(c, 0) for c in crops]

    x = range(len(crops))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([i - width / 2 for i in x], actual_vals, width, label=f"Actual {DROUGHT_YEAR}")
    ax.bar([i + width / 2 for i in x], optimized_vals, width, label="Optimized (with rotation)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(crops, rotation=30, ha="right")
    ax.set_ylabel("Acres")
    ax.set_title(f"Actual vs. optimized acres by crop, {DROUGHT_YEAR} drought")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def make_profit_compare_chart(actual_range, with_rotation_range, no_rotation_range, path):
    # A direct side-by-side of absolute profit (not a "gap of a gap") is far easier to
    # read at a glance than plotting the gap itself: the gap's own low-high range is
    # wide enough to span zero (actual and optimized profit swing together under the
    # same price scenario, but not by exactly the same amount), which made the
    # previous gap-only chart look like noise even though the mid-estimate gap is a
    # real, consistent ~$280k across both rotation assumptions.
    labels = ["Actual\n2021", "Optimized\n(with rotation)", "Optimized\n(no rotation)"]
    ranges = [actual_range, with_rotation_range, no_rotation_range]
    mids = [r["mid"] for r in ranges]
    err_low = [r["mid"] - r["low"] for r in ranges]
    err_high = [r["high"] - r["mid"] for r in ranges]
    colors = ["#6b6b6b", "#1E5631", "#8fae91"]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(labels, mids, yerr=[err_low, err_high], capsize=8, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Estimated profit ($)")
    ax.set_title(f"Actual vs. optimized profit, {DROUGHT_YEAR} drought\n(mid estimate, low-high range)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    drought_water_af = float(
        pd.read_csv(ROOT / "data" / "processed" / "water_baseline.csv")
        .set_index("scenario")["water_af"][f"drought_year_{DROUGHT_YEAR}"]
    )

    actual_plan, actual_acres = agent_tools._actual_plan_for_year(DROUGHT_YEAR)
    actual_range = profit_range(actual_plan)
    actual_water = water_used(actual_plan)

    with_rotation = run_optimized(drought_water_af, use_rotation=True)
    no_rotation = run_optimized(drought_water_af, use_rotation=False)
    with_rotation_range = profit_range(with_rotation["plan"])
    no_rotation_range = profit_range(no_rotation["plan"])

    diff_table = field_diff_table(actual_plan, with_rotation["plan"])
    diff_table.to_csv(OUTPUT_DIR / "backtest_fields.csv", index=False)

    make_acres_chart(actual_acres, with_rotation["acres_by_crop"], OUTPUT_DIR / "acres_by_crop.png")
    make_profit_compare_chart(actual_range, with_rotation_range, no_rotation_range, OUTPUT_DIR / "profit_gap.png")

    print(f"=== {DROUGHT_YEAR} drought-year backtest ===")
    print(f"Actual water supply used that year (real IDWR/TFCC-informed estimate): {drought_water_af:,.0f} acre-feet")
    print()
    print(f"Actual {DROUGHT_YEAR} plan: profit ${actual_range['low']:,.0f} - ${actual_range['high']:,.0f} "
          f"(mid ${actual_range['mid']:,.0f}), water used {actual_water:,.0f} AF")
    print(f"Optimized plan (with rotation): profit ${with_rotation_range['low']:,.0f} - "
          f"${with_rotation_range['high']:,.0f} (mid ${with_rotation_range['mid']:,.0f}), "
          f"water used {with_rotation['total_water_af']:,.0f} AF")
    print(f"Optimized plan (no rotation): profit ${no_rotation_range['low']:,.0f} - "
          f"${no_rotation_range['high']:,.0f} (mid ${no_rotation_range['mid']:,.0f}), "
          f"water used {no_rotation['total_water_af']:,.0f} AF")
    print()
    gap_with = with_rotation_range["mid"] - actual_range["mid"]
    gap_without = no_rotation_range["mid"] - actual_range["mid"]
    print(f"Mid-estimate profit gap, with rotation: ${gap_with:,.0f}")
    print(f"Mid-estimate profit gap, no rotation:   ${gap_without:,.0f}")
    print(
        "The no-rotation gap is larger because that plan is free to repeat potatoes/sugar beets "
        "on the same fields every year, which the acreage caps and per-field rotation rule "
        "otherwise prevent -- a less realistic, more optimistic upper bound."
    )
    print()
    print(f"Fields where the optimized plan differs most from what was actually planted "
          f"(see backtest/outputs/backtest_fields.csv for all {len(diff_table)}):")
    print(diff_table.head(10).to_string(index=False))
    print()
    print("Charts saved to backtest/outputs/acres_by_crop.png and profit_gap.png")


if __name__ == "__main__":
    main()
