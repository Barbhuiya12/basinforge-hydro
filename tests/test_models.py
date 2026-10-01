import builtins

import numpy as np
import pandas as pd
import pytest

from basinforge import Basin, get_model, list_models


def make_basin(model="GR4J", n=80, identifier="fixture", seed=12):
    step = get_model(model).timestep
    rng = np.random.default_rng(seed)
    frequency = {"daily": "D", "monthly": "MS", "annual": "YS"}[step]
    scale = {"daily": 1, "monthly": 20, "annual": 150}[step]
    return Basin(identifier, pd.date_range("2000-01-01", periods=n, freq=frequency), rng.gamma(1, 5, n) * scale, np.full(n, 2.0 * scale), temperature=5 + 10 * np.sin(np.arange(n) / 20), area_km2=150, timestep=step)


@pytest.mark.parametrize("name", ["GR4J", "HYMOD", "HBV", "MILC", "GR2M", "GR1A"])
def test_parity_with_lumod_public_api(name):
    lumod = pytest.importorskip("lumod")
    models = lumod.models
    basin = make_basin(name)
    fast = get_model(name).simulate(basin)
    frame = pd.DataFrame({"prec": basin.precipitation, "pet": basin.pet, "tmean": basin.temperature}, index=basin.dates)
    upstream = getattr(models, name)(area=basin.area_km2, lat=basin.latitude).run(frame).qt.to_numpy()
    if name in {"GR4J", "HYMOD", "HBV", "MILC"}:
        upstream = upstream * 86.4 / basin.area_km2
    np.testing.assert_allclose(fast, upstream, rtol=2e-6, atol=2e-6)
    assert np.all(fast >= 0)


def test_models_do_not_mutate_inputs_or_defaults():
    basin = make_basin()
    model = get_model("GR4J")
    before = dict(model.defaults)
    first = model.simulate(basin, {"x1": 600})
    second = model.simulate(basin, {"x1": 600})
    np.testing.assert_array_equal(first, second)
    assert model.defaults == before
    assert not basin.precipitation.flags.writeable


def test_python_models_run_without_upstream_runtime_packages(monkeypatch):
    original_import = builtins.__import__

    def forbid_upstream(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"lumod", "smartpy"}:
            raise AssertionError(f"Python model runtime tried to import optional reference package {name}.")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbid_upstream)
    for item in list_models():
        basin = make_basin(item["name"], n=40)
        output = get_model(item["name"]).simulate(basin)
        assert output.shape == basin.precipitation.shape
        assert np.all(np.isfinite(output))


def test_frequency_and_temperature_validation():
    with pytest.raises(ValueError, match="monthly"):
        get_model("GR2M").simulate(make_basin())
    from dataclasses import replace
    with pytest.raises(ValueError, match="temperature"):
        get_model("HBV").simulate(replace(make_basin(), temperature=None))
    with pytest.raises(ValueError, match="Unknown"):
        get_model("GR4J").simulate(make_basin(), {"not_a_parameter": 1})
    with pytest.raises(ValueError, match="fraction"):
        get_model("GR4J").simulate(make_basin(), {"ps0": -1})


def test_list_is_actual_supported_models():
    assert len(list_models()) == 14
    assert len(list_models(include_optional=True)) == 61
    assert "modified" in get_model("HYMOD").variant
