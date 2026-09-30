from dataclasses import replace
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from basinforge import Basin, CalibrationConfig, calibrate, calibrate_many, check_marrmot, get_model, marrmot_details
from basinforge.marrmot import EngineUnavailableError, MarrmotRunner
from test_models import make_basin


enabled = os.environ.get("BASINFORGE_TEST_MARRMOT") == "1"
integration = pytest.mark.skipif(not enabled, reason="Set BASINFORGE_TEST_MARRMOT=1 with octave-cli + optim installed")


def test_missing_external_runtime_has_actionable_error():
    runner = MarrmotRunner("m_01_collie1_1p_1s", 1, 1, executable="basinforge-nonexistent-octave")
    with pytest.raises(EngineUnavailableError, match="requires octave-cli"):
        runner(make_basin(), {"p01": 1000, "s01": 0})


def test_marrmot_snow_requires_temperature_but_hymod_does_not():
    basin = replace(make_basin(), temperature=None)
    get_model("MARRMOT_29").validate_basin(basin)
    with pytest.raises(ValueError, match="temperature"):
        get_model("MARRMOT_37").validate_basin(basin)


@integration
def test_runtime_preflight_all_classes():
    result = check_marrmot()
    assert len(result["models"]) == 47


@integration
@pytest.mark.parametrize("number", range(1, 48))
def test_every_marrmot_model_against_independent_upstream(number):
    reference = json.loads((Path(__file__).parent / "fixtures" / "upstream_outputs.json").read_text())
    forcing = reference["forcing"]
    basin = Basin("reference", pd.date_range("2000-01-01", periods=30), forcing["precipitation"], forcing["pet"], temperature=forcing["temperature"])
    model = get_model(f"MARRMOT_{number:02d}")
    actual = model.runner(basin, model.parameters())
    expected = reference["marrmot"][model.runner.class_name]
    # Native MARRMoT may emit tiny negative roundoff; adapter clips only up
    # to 1e-8 mm and exposes raw results through marrmot_details.
    np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-8)
    if min(expected) < -1e-8:
        # Upstream Sacramento emits negative flow on this empty-store dry
        # fixture. Verify parity AND that the safe public API rejects it.
        with pytest.raises(RuntimeError, match="invalid discharge"):
            model.simulate(basin)
    else:
        assert np.all(actual >= 0)


@integration
def test_random_fallback_is_independent_of_request_history():
    basin = make_basin(n=30)
    model = get_model("MARRMOT_33")
    first = model.runner(basin, model.parameters()).copy()
    get_model("MARRMOT_37").runner(basin, get_model("MARRMOT_37").parameters())
    np.testing.assert_array_equal(first, model.runner(basin, model.parameters()))


@integration
def test_real_calibration_path_and_continuous_state():
    basin = make_basin(n=40)
    basin = replace(basin, precipitation=basin.precipitation * 30)
    model = get_model("MARRMOT_29")
    basin = replace(basin, qobs=model.simulate(basin))
    config = CalibrationConfig(method="lhs", samples=3, warmup=5, calibration_fraction=0.7, bounds={"p01": model.bounds["p01"]})
    fit = calibrate(basin, model, config)
    assert fit.validation_metrics is not None
    np.testing.assert_array_equal(fit.simulated, model.simulate(basin, fit.parameters))
    details = marrmot_details(basin, model, fit.parameters)
    assert np.isfinite(details["water_balance_error_mm"])
    assert details["solver_residuals"].shape == (40,)
    assert len(details["stores_mm"]) == 5


@integration
def test_spawned_marrmot_basins_match_serial():
    first = make_basin(identifier="A", n=20)
    first = replace(first, precipitation=first.precipitation*20)
    first = replace(first, qobs=get_model("MARRMOT_29").simulate(first))
    second = replace(first, basin_id="B")
    config = CalibrationConfig(method="lhs", samples=2, warmup=3, bounds={"p01": (100, 1000)})
    serial = calibrate_many([first, second], "MARRMOT_29", config)
    parallel = calibrate_many([first, second], "MARRMOT_29", config, workers=2)
    assert not serial["errors"] and not parallel["errors"]
    for key in serial["results"]:
        assert serial["results"][key].parameters == parallel["results"][key].parameters


@integration
@pytest.mark.parametrize("number", range(1, 48))
def test_every_marrmot_adapter_enters_calibration(number):
    basin = make_basin(n=20)
    basin = replace(basin, precipitation=basin.precipitation*30)
    model = get_model(f"MARRMOT_{number:02d}")
    basin = replace(basin, qobs=model.simulate(basin))
    key = next(iter(model.bounds))
    # RMSE remains defined for short-record zero flow in long-lag models.
    # This is an optimizer-interface test, not a claim of predictive skill.
    fit = calibrate(basin, model, CalibrationConfig(method="lhs", samples=2, objective="rmse", warmup=3, calibration_fraction=.7, bounds={key: model.bounds[key]}))
    assert np.isfinite(fit.objective_loss) and fit.evaluations == 2
