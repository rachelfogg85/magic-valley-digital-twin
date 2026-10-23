"""Small, hand-checkable tests for optimizer/lp.py."""
from lp import solve


def test_picks_the_more_profitable_crop_when_water_is_ample():
    crop_params = {
        "CropA": {"price_mid": 10, "yield_mid": 10, "cost_per_acre": 50, "water_af_per_acre": 1},
        "CropB": {"price_mid": 5, "yield_mid": 5, "cost_per_acre": 5, "water_af_per_acre": 0.5},
        "Fallow": {"price_mid": 0, "yield_mid": 0, "cost_per_acre": 0, "water_af_per_acre": 0},
    }
    # CropA profit/acre = 10*10-50 = 50; CropB = 5*5-5 = 20; CropA should win.
    fields = [{"field_id": "F1", "acres": 10}]
    result = solve(fields, crop_params, water_limit_af=100, use_rotation=False)

    assert result["plan"] == {"F1": "CropA"}
    assert result["total_profit"] == 500
    assert result["total_water_af"] == 10


def test_everything_goes_fallow_when_water_is_zero():
    crop_params = {
        "CropA": {"price_mid": 10, "yield_mid": 10, "cost_per_acre": 50, "water_af_per_acre": 1},
        "CropB": {"price_mid": 5, "yield_mid": 5, "cost_per_acre": 5, "water_af_per_acre": 0.5},
        "Fallow": {"price_mid": 0, "yield_mid": 0, "cost_per_acre": 0, "water_af_per_acre": 0},
    }
    fields = [{"field_id": "F1", "acres": 10}, {"field_id": "F2", "acres": 20}]
    result = solve(fields, crop_params, water_limit_af=0, use_rotation=False)

    assert result["plan"] == {"F1": "Fallow", "F2": "Fallow"}
    assert result["total_profit"] == 0
    assert result["total_water_af"] == 0
    assert "water" in result["binding_constraints"]


def test_rotation_blocks_potatoes_grown_too_recently():
    crop_params = {
        # Potatoes is the most profitable option (50/acre) but was grown last year.
        "Potatoes": {"price_mid": 10, "yield_mid": 10, "cost_per_acre": 50, "water_af_per_acre": 1},
        "Corn": {"price_mid": 5, "yield_mid": 5, "cost_per_acre": -15, "water_af_per_acre": 0.5},
        "Fallow": {"price_mid": 0, "yield_mid": 0, "cost_per_acre": 0, "water_af_per_acre": 0},
    }
    fields = [{"field_id": "F1", "acres": 10}]
    history = {"F1": {2020: "Potatoes"}}  # within the 3-year potato rotation window

    result = solve(
        fields, crop_params, water_limit_af=1000, year=2021,
        use_rotation=True, history=history,
    )

    assert result["plan"] == {"F1": "Corn"}


def test_rotation_allows_potatoes_once_outside_the_window():
    crop_params = {
        "Potatoes": {"price_mid": 10, "yield_mid": 10, "cost_per_acre": 50, "water_af_per_acre": 1},
        "Corn": {"price_mid": 5, "yield_mid": 5, "cost_per_acre": -15, "water_af_per_acre": 0.5},
        "Fallow": {"price_mid": 0, "yield_mid": 0, "cost_per_acre": 0, "water_af_per_acre": 0},
    }
    fields = [{"field_id": "F1", "acres": 10}]
    history = {"F1": {2017: "Potatoes"}}  # 4 years before 2021: outside the 3-year window

    result = solve(
        fields, crop_params, water_limit_af=1000, year=2021,
        use_rotation=True, history=history,
    )

    assert result["plan"] == {"F1": "Potatoes"}


def test_sugar_beet_contract_cap_limits_total_acreage():
    crop_params = {
        "Sugar Beets": {"price_mid": 10, "yield_mid": 20, "cost_per_acre": 50, "water_af_per_acre": 1},
        "Corn": {"price_mid": 5, "yield_mid": 10, "cost_per_acre": 10, "water_af_per_acre": 0.5},
        "Fallow": {"price_mid": 0, "yield_mid": 0, "cost_per_acre": 0, "water_af_per_acre": 0},
    }
    fields = [{"field_id": "F1", "acres": 100}, {"field_id": "F2", "acres": 100}]

    result = solve(
        fields, crop_params, water_limit_af=1000, year=2021,
        use_rotation=True, history={}, acreage_caps={"Sugar Beets": 100},
    )

    assert result["acres_by_crop"].get("Sugar Beets", 0) == 100
    assert result["acres_by_crop"].get("Corn", 0) == 100
    assert result["total_profit"] == 150 * 100 + 40 * 100
    assert "sugar_beets_contract_cap" in result["binding_constraints"]


if __name__ == "__main__":
    test_picks_the_more_profitable_crop_when_water_is_ample()
    test_everything_goes_fallow_when_water_is_zero()
    test_rotation_blocks_potatoes_grown_too_recently()
    test_rotation_allows_potatoes_once_outside_the_window()
    test_sugar_beet_contract_cap_limits_total_acreage()
    print("All optimizer tests passed.")
