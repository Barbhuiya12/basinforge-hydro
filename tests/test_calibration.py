from dataclasses import replace
import json

import numpy as np
import pandas as pd
import pytest

from basinforge import CalibrationConfig, calibrate, calibrate_many, calibrate_shared, compare_models, get_model
from test_models import make_basin


def observed(identifier="B", seed=12):
    basin = make_basin(n=100, identifier=identifier, seed=seed)
    return replace(basin, qobs=get_model("GR4J").simulate(basin, {"x1": 700}))


def config(**kwargs):
    return CalibrationConfig(warmup=10, maxiter=1, popsize=5, calibration_end="2000-03-10", **kwargs)


def test_deterministic_fit_and_continuous_validation():
    basin = observed()
    fit = calibrate(basin, config=config())
    again = calibrate(basin, config=config())
    assert fit.parameters == again.parameters
    assert fit.objective_loss == again.objective_loss
    assert fit.validation_metrics is not None
    np.testing.assert_array_equal(fit.simulated, get_model("GR4J").simulate(basin, fit.parameters))
    assert fit.evaluations > 0
    assert fit.converged is False
    assert len(fit.history) == 1


def test_validation_observations_cannot_affect_calibration():
    basin = observed()
    values = basin.qobs.copy()
    values[basin.dates > "2000-03-10"] *= 100
    a = calibrate(basin, config=config())
    b = calibrate(replace(basin, qobs=values), config=config())
    assert a.parameters == b.parameters
    assert a.objective_loss == b.objective_loss


def test_lhs_and_fixed_parameters():
    c = CalibrationConfig(method="lhs", samples=10, warmup=10, bounds={"x1": (100, 1000)}, fixed={"x2": 1})
    fit = calibrate(observed(), config=c)
    assert fit.parameters["x2"] == 1
    assert fit.evaluations == 10
    assert not fit.converged


def test_shared_equal_weight_and_independent_basins():
    basins = [observed("A"), observed("B", seed=13)]
    fit = calibrate_shared(basins, config=config())
    assert set(fit["basins"]) == {"A", "B"}
    assert fit["evaluations"] > 0
    for basin in basins:
        np.testing.assert_array_equal(fit["basins"][basin.basin_id]["simulated"], get_model("GR4J").simulate(basin, fit["parameters"]))


def test_batch_resume_and_changed_data_protection(tmp_path):
    basins = [observed("A/../unsafe"), observed("B")]
    output = tmp_path / "results"
    first = calibrate_many(basins, config=config(), output=output)
    assert not first["errors"]
    assert len(list(output.glob("*/fit.json"))) == 2
    second = calibrate_many(basins, config=config(), output=output, resume=True)
    assert len(second["resumed"]) == 2
    for identifier in first["results"]:
        np.testing.assert_allclose(first["results"][identifier].simulated, second["results"][identifier].simulated)
    changed = calibrate_many(basins, config=config(seed=999), output=output, resume=True)
    assert len(changed["errors"]) == 2
    assert all("different data" in error for error in changed["errors"].values())


def test_parallel_matches_serial():
    basins = [observed("A"), observed("B")]
    sequential = calibrate_many(basins, config=config())
    parallel = calibrate_many(basins, config=config(), workers=2)
    assert not parallel["errors"]
    for identifier in sequential["results"]:
        assert sequential["results"][identifier].parameters == parallel["results"][identifier].parameters


def test_no_overlapping_validation_and_insufficient_warmup():
    with pytest.raises(ValueError, match="overlap"):
        calibrate(observed(), config=config(validation_start="2000-03-01"))
    with pytest.raises(ValueError, match="warmup"):
        calibrate(observed(), config=CalibrationConfig(warmup=100))


def test_batch_isolates_failure_and_comparison_honest():
    good = observed("good")
    bad = replace(observed("bad"), qobs=np.zeros(100))
    batch = calibrate_many([good, bad], config=config())
    assert set(batch["results"]) == {"good"}
    assert set(batch["errors"]) == {"bad"}
    comparison = compare_models([good], ["GR4J", "GR2M"], config=config())
    assert "_model" in comparison["GR2M"]["errors"]


def test_fraction_split_with_different_calendar_coverage():
    first = observed("early")
    second = replace(observed("later"), dates=pd.date_range("2010-01-01", periods=len(first.dates), freq="D"))
    c = CalibrationConfig(warmup=10, calibration_fraction=0.7, maxiter=0, popsize=5)
    batch = calibrate_many([first, second], config=c)
    assert not batch["errors"]
    assert all(fit.validation_metrics is not None for fit in batch["results"].values())
    changed = second.qobs.copy()
    changed[70:] *= 100
    fit = calibrate(replace(second, qobs=changed), config=c)
    assert fit.parameters == batch["results"]["later"].parameters
    for fraction in (0, 1, float("nan")):
        with pytest.raises(ValueError, match="calibration_fraction"):
            CalibrationConfig(calibration_fraction=fraction)
    with pytest.raises(ValueError, match="not both"):
        CalibrationConfig(calibration_fraction=0.7, calibration_end="2000-03-10")
