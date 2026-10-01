from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from basinforge import CalibrationConfig, calibrate, calibrate_multistart, export_report, get_model, list_models, simulate_ensemble
from basinforge.water_balance import abcd_components
from test_models import make_basin
from test_calibration import observed


@pytest.mark.parametrize("name", ["GR3J", "GR5J", "GR6J", "HYMOD_CLASSIC", "XAJ", "XAJ_MZ", "SMART", "ABCD"])
def test_new_engine_run_and_calibration(name):
    basin = make_basin(name, n=60)
    model = get_model(name)
    before = basin.precipitation.copy()
    output = model.simulate(basin)
    np.testing.assert_array_equal(output, model.simulate(basin))
    assert np.all(np.isfinite(output)) and np.all(output >= 0)
    np.testing.assert_array_equal(before, basin.precipitation)
    # Fit one noninteger parameter so every adapter actually exercises the
    # shared calibration code, not just a stand-alone simulation shortcut.
    key = next(iter(model.bounds))
    fit = calibrate(replace(basin, qobs=output), model, CalibrationConfig(method="lhs", samples=3, warmup=5, calibration_fraction=0.7, bounds={key: model.bounds[key]}))
    assert fit.evaluations == 3
    assert fit.validation_metrics is not None


def test_abcd_equations_and_mass_balance():
    precipitation = np.array([0., 20., 500., 0., 5., 150.])
    pet = np.array([2., 5., 10., 20., 5., 10.])
    a, b, c, d = 0.95, 250., 0.5, 0.1
    q, aet, soil, groundwater = abcd_components(precipitation, pet, a, b, c, d)
    previous = np.r_[0, (soil + groundwater)[:-1]]
    np.testing.assert_allclose(previous + precipitation, q + aet + soil + groundwater, atol=1e-10)
    # Independent literal form of the published root, not the optimized
    # rationalized implementation used by the package.
    old_soil = old_ground = 0.0
    expected = []
    for p, e in zip(precipitation, pet):
        w = old_soil + p
        y = (w + b)/(2*a) - np.sqrt(((w + b)/(2*a))**2 - b*w/a)
        old_soil = y*np.exp(-e/b)
        old_ground = (old_ground + c*(w-y))/(1+d)
        expected.append((1-c)*(w-y) + d*old_ground)
    np.testing.assert_allclose(q, expected, atol=1e-10)


def test_smart_parity_with_hourly_upstream_run():
    smartpy = pytest.importorskip("smartpy.structure")
    run_all_steps = smartpy.run_all_steps
    basin = make_basin("SMART", n=10)
    model = get_model("SMART")
    parameters = np.array([model.defaults[name] for name in ["T", "C", "H", "D", "S", "Z", "SK", "FK", "GK", "RK"]])
    initial = np.zeros(19)
    initial[12:18] = model.defaults["Z"]/12/1000*basin.area_km2*1e6
    # Upstream public routine with exactly the same stated hourly forcing
    # assumption and state initialization; returned flow is mean m³/s.
    q, _, _ = run_all_steps(basin.area_km2*1e6, 3600, len(basin.dates)*24, np.repeat(basin.precipitation/24, 24), np.repeat(basin.pet/24, 24), parameters, initial, 1, 24)
    np.testing.assert_allclose(model.simulate(basin), q*86.4/basin.area_km2, rtol=1e-12, atol=1e-12)


def test_multistart_selects_only_training_and_ensemble():
    basin = observed()
    config = CalibrationConfig(warmup=10, calibration_fraction=0.7, maxiter=0, popsize=5)
    search = calibrate_multistart(basin, config=config, seeds=[1, 2])
    assert search["best"].objective_loss == min(fit.objective_loss for fit in search["trials"])
    values = basin.qobs.copy()
    values[70:] *= 100
    again = calibrate_multistart(replace(basin, qobs=values), config=config, seeds=[1, 2])
    assert again["best"].parameters == search["best"].parameters
    ensemble = simulate_ensemble(basin, "GR4J", [fit.parameters for fit in search["trials"]])
    assert ensemble["simulations_mm"].shape == (2, 100)
    np.testing.assert_allclose(ensemble["quantiles_mm"], np.quantile(ensemble["simulations_mm"], [.05, .5, .95], axis=0))
    with pytest.raises(ValueError):
        simulate_ensemble(basin, "GR4J", [], quantiles=[.5])


def test_report_fingerprint_and_html_escaping(tmp_path):
    basin = observed("<script>alert(1)</script>")
    fit = calibrate(basin, config=CalibrationConfig(warmup=10, calibration_fraction=0.7, maxiter=0))
    path = export_report(basin, fit, tmp_path / "report")
    assert path.exists() and (path.parent / "diagnostics.png").stat().st_size > 0
    assert "<script>" not in path.read_text()
    assert "&lt;script&gt;" in path.read_text()
    with pytest.raises(FileExistsError):
        export_report(basin, fit, path.parent)
    with pytest.raises(ValueError, match="does not match"):
        export_report(replace(basin, pet=basin.pet + 1), fit, tmp_path / "bad")


def test_inventory_is_explicit_and_does_not_mutate_defaults():
    models = list_models(include_optional=True)
    assert len(models) == 61
    assert sum(model["backend"] == "octave" for model in models) == 47
    models[0]["defaults"]["x1"] = -999
    assert get_model("GR4J").defaults["x1"] > 0


@pytest.mark.parametrize("name,key", [("GR3J", "gr3j"), ("GR5J", "gr5j"), ("GR6J", "gr6j"), ("HYMOD_CLASSIC", "hymod"), ("XAJ", "xaj"), ("XAJ_MZ", "xaj_mz")])
def test_hydromodel_against_independent_checkout_reference(name, key):
    import pandas as pd
    from basinforge import Basin
    reference = json.loads((Path(__file__).parent / "fixtures" / "upstream_outputs.json").read_text())
    forcing = reference["forcing"]
    basin = Basin("reference", pd.date_range("2000-01-01", periods=30), forcing["precipitation"], forcing["pet"])
    case = reference["hydromodel"][key]
    np.testing.assert_allclose(get_model(name).simulate(basin, case["parameters"]), case["qsim_mm"], rtol=1e-10, atol=1e-10)
