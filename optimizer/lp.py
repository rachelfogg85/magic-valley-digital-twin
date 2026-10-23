"""Linear program: pick the most profitable crop (or fallow) for each field under a
water limit and simple rotation rules.

This is the single source of truth used by both the live app (server/app.py) and the
backtest (backtest/run_backtest.py) -- both call solve() so the "plan" shown on the
map and the backtest's "optimal" comparison are always computed the same way.
"""
import pulp

ROTATION_YEARS = {"Potatoes": 3, "Sugar Beets": 2}


def solve(
    fields,
    crop_params,
    water_limit_af,
    year=None,
    price_case="mid",
    use_rotation=True,
    history=None,
    acreage_caps=None,
):
    """
    fields: list of {"field_id": str, "acres": float}
    crop_params: dict crop_name -> {price_low/mid/high, yield_low/mid/high,
                 cost_per_acre, water_af_per_acre} (must include "Fallow": all zeros)
    water_limit_af: total acre-feet available this scenario
    price_case: "low" | "mid" | "high"
    use_rotation: enforce the potato/sugar-beet rotation rules below
    history: dict field_id -> {year: crop_name}, real past plantings, used only when
             use_rotation is True
    acreage_caps: dict crop_name -> max total acres across all fields (processor
             contract limits, e.g. {"Sugar Beets": 750, "Potatoes": 600}), or None

    Returns: {
      "plan": {field_id: crop_name},
      "total_profit": float, "total_water_af": float,
      "acres_by_crop": {crop: acres},
      "binding_constraints": [str],
    }
    """
    crops = list(crop_params.keys())
    history = history or {}

    prob = pulp.LpProblem("crop_plan", pulp.LpMaximize)

    x = {
        (f["field_id"], c): pulp.LpVariable(f"x_{f['field_id']}_{c}", cat="Binary")
        for f in fields
        for c in crops
    }

    for f in fields:
        prob += pulp.lpSum(x[(f["field_id"], c)] for c in crops) == 1

    def profit_per_acre(crop):
        p = crop_params[crop]
        return p[f"price_{price_case}"] * p[f"yield_{price_case}"] - p["cost_per_acre"]

    prob += pulp.lpSum(
        x[(f["field_id"], c)] * f["acres"] * profit_per_acre(c) for f in fields for c in crops
    )

    water_expr = pulp.lpSum(
        x[(f["field_id"], c)] * f["acres"] * crop_params[c]["water_af_per_acre"]
        for f in fields
        for c in crops
    )
    prob += water_expr <= water_limit_af

    if use_rotation:
        for f in fields:
            fid = f["field_id"]
            field_hist = history.get(fid, {})
            for crop, years_back in ROTATION_YEARS.items():
                if crop not in crop_params:
                    continue
                if year is not None:
                    recent = [field_hist.get(year - i) for i in range(1, years_back + 1)]
                else:
                    recent = []
                if crop in recent:
                    prob += x[(fid, crop)] == 0

        for crop, cap in (acreage_caps or {}).items():
            if crop in crop_params:
                prob += (
                    pulp.lpSum(x[(f["field_id"], crop)] * f["acres"] for f in fields) <= cap
                )

    # With ~100 near-identical fields, acreage caps create massive MIP symmetry --
    # huge numbers of equally-good "which fields get the capped crop" solutions --
    # which can make CBC spend minutes proving optimality to the last dollar. A
    # short time limit plus a 1% gap tolerance keeps scenarios fast (course requires
    # under 2s) without meaningfully changing the plan: our price/yield inputs are
    # themselves rough low/mid/high estimates, so sub-1% precision is false rigor.
    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=1.5, gapRel=0.01))

    plan = {}
    acres_by_crop = {c: 0.0 for c in crops}
    total_water = 0.0
    for f in fields:
        for c in crops:
            if pulp.value(x[(f["field_id"], c)]) > 0.5:
                plan[f["field_id"]] = c
                acres_by_crop[c] += f["acres"]
                total_water += f["acres"] * crop_params[c]["water_af_per_acre"]
                break

    # A near-but-not-exact match to a cap is normal here (whole fields of uneven
    # acreage can't always fill a continuous limit exactly), so "binding" uses a
    # small relative tolerance rather than exact equality.
    def near(value, limit, rel_tol=0.01):
        return limit <= 0 or value >= limit * (1 - rel_tol)

    binding = []
    if near(total_water, water_limit_af):
        binding.append("water")
    if use_rotation:
        for crop, cap in (acreage_caps or {}).items():
            if near(acres_by_crop.get(crop, 0), cap):
                binding.append(f"{crop.lower().replace(' ', '_')}_contract_cap")

    return {
        "plan": plan,
        "total_profit": round(pulp.value(prob.objective), 2),
        "total_water_af": round(total_water, 2),
        "acres_by_crop": {c: round(a, 1) for c, a in acres_by_crop.items() if a > 0},
        "binding_constraints": binding,
        "status": pulp.LpStatus[prob.status],
    }
