"""Precisely identified additional engines with no hidden upstream warmup."""
from importlib import import_module

import numpy as np

from .models import Model


def _hydromodel_run(basin, params, key):
    from ._vendor.hydromodel.model_config import MODEL_PARAM_DICT
    function = getattr(import_module(f"basinforge._vendor.hydromodel.{ 'xaj' if key.startswith('xaj') else key}"), "xaj" if key.startswith("xaj") else key)
    contract = MODEL_PARAM_DICT[key]
    forcing = np.column_stack((basin.precipitation, basin.pet))[:, None, :]
    vector = np.array([[params[name] for name in contract["param_name"]]])
    result = function(forcing, vector, warmup_length=0, normalized_params=False, param_config={key: contract}, name=key, time_interval_hours=24)
    return np.asarray(result[0])[:, 0, 0]


def _gr3j(b, p):
    return _hydromodel_run(b, p, "gr3j")


def _gr5j(b, p):
    return _hydromodel_run(b, p, "gr5j")


def _gr6j(b, p):
    return _hydromodel_run(b, p, "gr6j")


def _hymod_classic(b, p):
    return _hydromodel_run(b, p, "hymod")


def _xaj(b, p):
    return _hydromodel_run(b, p, "xaj")


def _xaj_mz(b, p):
    return _hydromodel_run(b, p, "xaj_mz")


def _smart(b, p):
    # Force the documented Python implementation, not an unpinned smartcpp
    # extension that happens to be installed on the caller's machine.
    from smartpy.structure import run_one_step_catchment, run_one_step_river
    area = b.area_km2 * 1e6
    states = np.zeros(12)
    states[5:11] = p["Z"] / 12 / 1000 * area
    names = ["T", "C", "H", "D", "S", "Z", "SK", "FK", "GK"]
    values = [p[name] for name in names]
    result = np.empty(len(b.dates))
    # SMART routing time constants are hourly. Daily totals are apportioned
    # uniformly across 24 hourly substeps, not passed as hourly rainfall.
    for i in range(len(result)):
        volume = 0.0
        for _ in range(24):
            out = run_one_step_catchment(area, 3600.0, b.precipitation[i] / 24, b.pet[i] / 24, *values, *states[:11])
            channel_in = sum(out[1:6])
            channel_out, river_state = run_one_step_river(3600.0, channel_in, p["RK"], states[11])
            states[:11] = out[6:]
            states[11] = river_state
            volume += channel_out * 3600
        result[i] = volume / area * 1000
    return result


def extended_registry():
    from ._vendor.hydromodel.model_config import MODEL_PARAM_DICT
    entries = [
        ("GR3J", "gr3j", _gr3j),
        ("GR5J", "gr5j", _gr5j),
        ("GR6J", "gr6j", _gr6j),
        ("HYMOD_CLASSIC", "hymod", _hymod_classic),
        ("XAJ", "xaj", _xaj),
        ("XAJ_MZ", "xaj_mz", _xaj_mz),
    ]
    result = {}
    for name, key, runner in entries:
        bounds = {k: tuple(v) for k, v in MODEL_PARAM_DICT[key]["param_range"].items()}
        # Exclude singular zero-capacity/time-scale boundaries, not change
        # model equations. L remains an upstream rounded lag parameter.
        if key.startswith("xaj"):
            bounds["UM"] = (0.1, bounds["UM"][1])
            bounds["KI"] = (0.001, bounds["KI"][1])
            bounds["KG"] = (0.001, bounds["KG"][1])
        if key == "xaj_mz":
            bounds["A"] = (0.1, bounds["A"][1])
            bounds["THETA"] = (0.1, bounds["THETA"][1])
        defaults = {k: (low + high) / 2 for k, (low, high) in bounds.items()}
        result[name] = Model(name, "daily", defaults, bounds, runner, f"hydromodel 0.4.0 source rev 89d7a8e {key}; upstream numerical variant; initial states unchanged")
    bounds = {"T": (0.9, 1.1), "C": (0, 1), "H": (0, 0.3), "D": (0, 1), "S": (0, 0.013), "Z": (15, 150), "SK": (1, 240), "FK": (48, 1440), "GK": (1200, 4800), "RK": (1, 96)}
    result["SMART"] = Model("SMART", "daily", {k: sum(v) / 2 for k, v in bounds.items()}, bounds, _smart, "SMARTpy 0.2.2 Python equations; uniform hourly disaggregation of daily P/PET; half-full soil, empty routing stores")
    from .water_balance import water_balance_registry
    result.update(water_balance_registry())
    return result
