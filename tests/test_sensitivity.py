from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from basinforge import Basin, CalibrationConfig, Model, morris_sensitivity, run_experiment, sobol_sensitivity


def problem():
    dates = pd.date_range("2001-01-01", periods=80, freq="D")
    precipitation = 3 + 2 * np.sin(np.arange(80) * 0.17) ** 2
    pet = 1 + np.cos(np.arange(80) * 0.11) ** 2
    qobs = 0.7 * precipitation + 0.25 * pet + 0.03 * np.sin(np.arange(80))
    basin = Basin("sensitivity-test", dates, precipitation, pet, qobs, area_km2=10)
    # An exactly controlled, deterministic conceptual response: x has a
    # known larger influence than y within the specified ranges.
    model = Model("LINEAR_TEST", "daily", {"x": 0.5, "y": 0.5}, {"x": (0.1, 1.0), "y": (0.1, 1.0)}, lambda b, p: p["x"] * b.precipitation + p["y"] * b.pet, "test equation")
    return basin, model


def test_morris_is_repeatable_and_scores_training_only():
    basin, model = problem()
    config = CalibrationConfig(warmup=5, calibration_fraction=0.7, fixed={})
    first = morris_sensitivity(basin, model, config, trajectories=8, levels=4, seed=31)
    second = morris_sensitivity(basin, model, config, trajectories=8, levels=4, seed=31)
    assert first == second
    assert first["evaluations"] == 8 * 3
    assert first["training_steps"] == int(80 * 0.7) - 5
    assert first["parameters"][0]["parameter"] == "x"
    assert first["parameters"][0]["mu_star"] > first["parameters"][1]["mu_star"]
    validation_changed = replace(basin, qobs=np.r_[basin.qobs[:56], np.full(24, 1e6)])
    assert first == morris_sensitivity(validation_changed, model, config, trajectories=8, levels=4, seed=31)


def test_sobol_estimators_recover_dominant_parameter_and_are_repeatable():
    basin, model = problem()
    config = CalibrationConfig(warmup=5, calibration_fraction=0.7)
    first = sobol_sensitivity(basin, model, config, samples=256, seed=8, bootstrap=100)
    second = sobol_sensitivity(basin, model, config, samples=256, seed=8, bootstrap=100)
    assert first == second
    assert first["evaluations"] == 256 * 4
    assert first["parameters"][0]["parameter"] == "x"
    assert first["parameters"][0]["total_order"] > first["parameters"][1]["total_order"]
    assert first["parameters"][0]["first_order"] > 0.5
    for item in first["parameters"]:
        assert 0 <= item["total_order"] <= 1.5
        assert len(item["total_order_ci95"]) == 2


@pytest.mark.parametrize("kwargs", [{"samples": 12}, {"samples": 2}, {"bootstrap": -1}])
def test_sobol_rejects_invalid_budgets(kwargs):
    basin, model = problem()
    with pytest.raises(ValueError):
        sobol_sensitivity(basin, model, CalibrationConfig(warmup=2), **kwargs)


def test_one_call_experiment_exports_complete_results(tmp_path):
    from basinforge import get_model

    basin = replace(problem()[0], qobs=None)
    simulated = get_model("GR4J").simulate(basin)
    basin = replace(basin, qobs=simulated + 0.1 * np.sin(np.arange(len(simulated))))
    output = tmp_path / "one-call-study"
    result = run_experiment(
        basin,
        "GR4J",
        CalibrationConfig(method="lhs", samples=4, warmup=5, calibration_fraction=0.7, bounds={"x1": [100, 1500]}),
        sensitivity="morris",
        sensitivity_options={"trajectories": 2, "seed": 4},
        output=output,
    )
    assert result["fit"].validation_metrics is not None
    assert result["sensitivity"]["score_period"] == "training data after warmup only"
    assert (output / "fit/fit.json").exists()
    assert (output / "fit/simulation.csv").exists()
    assert (output / "report/index.html").exists()
    assert (output / "report/diagnostics.png").exists()
    assert (output / "sensitivity.json").exists()
    with pytest.raises(FileExistsError):
        run_experiment(basin, "GR4J", CalibrationConfig(method="lhs", samples=3, warmup=5), sensitivity=None, output=output)
