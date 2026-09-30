"""Fast array adapters to pinned LuMod kernels; no equations are relabelled."""
from dataclasses import dataclass
from typing import Callable
import warnings

import numpy as np

from .data import Basin


@dataclass(frozen=True)
class Model:
    name: str
    timestep: str
    defaults: dict
    bounds: dict
    runner: Callable
    variant: str
    temperature_required: bool = False
    backend: str = "python"

    def parameters(self, overrides=None):
        overrides = overrides or {}
        unknown = set(overrides) - set(self.defaults)
        if unknown:
            raise ValueError(f"Unknown {self.name} parameters: {sorted(unknown)}")
        values = dict(self.defaults, **overrides)
        if not all(np.isfinite(v) for v in values.values()):
            raise ValueError("All parameters must be finite.")
        for key, (low, high) in self.bounds.items():
            if not low <= values[key] <= high:
                raise ValueError(f"{key} outside supported range [{low}, {high}].")
        for key in {"ps0", "rs0", "s0", "r0", "w0"} & values.keys():
            if not 0 <= values[key] <= 1:
                raise ValueError(f"{key} must be a fraction in [0, 1].")
        for key in {"snow0", "wq0", "ws0", "w01", "w02", "soil0", "groundwater0"} & values.keys():
            if values[key] < 0:
                raise ValueError(f"{key} must be nonnegative.")
        if "nres" in values and (values["nres"] != int(values["nres"]) or not 1 <= values["nres"] <= 10):
            raise ValueError("nres must be an integer from 1 to 10.")
        return values

    def validate_basin(self, basin):
        if basin.timestep != self.timestep:
            raise ValueError(f"{self.name} requires {self.timestep} forcings; got {basin.timestep}.")
        if self.temperature_required and basin.temperature is None:
            raise ValueError(f"{self.name} requires temperature in Celsius.")
        if self.name == "GR1A" and np.any(basin.pet <= 0):
            raise ValueError("GR1A requires positive annual PET.")

    def simulate(self, basin: Basin, params=None):
        self.validate_basin(basin)
        result = np.asarray(self.runner(basin, self.parameters(params)), dtype=np.float64)
        if result.shape != basin.precipitation.shape or not np.all(np.isfinite(result)) or np.any(result < -1e-8):
            raise RuntimeError(f"{self.name} returned invalid discharge; check parameters/forcings.")
        return result


def _gr4j(b, p):
    from lumod.models.gr4j_model import _gr4j
    return _gr4j(b.precipitation, b.pet, *[p[k] for k in ["x1", "x2", "x3", "x4", "ps0", "rs0"]])[0]


def _gr2m(b, p):
    from lumod.models.gr2m_model import _gr2m
    return _gr2m(b.precipitation, b.pet, *[p[k] for k in ["s0", "r0", "x1", "x2"]])[0]


def _gr1a(b, p):
    from lumod.models.gr1a_model import _gr1a
    return _gr1a(b.precipitation, b.pet, p["x"])


def _hymod(b, p):
    from lumod.models.hymod_model import _hymod
    return _hymod(b.precipitation, b.pet, b.area_km2, *[p[k] for k in ["wmax", "w0", "wq0", "ws0", "alpha", "beta", "cexp", "nres", "ks", "kq", "kmax", "llet"]])[0] * 86.4 / b.area_km2


def _hbv(b, p):
    from lumod.models.hbv_model import _hbv_light
    return _hbv_light(b.precipitation, b.temperature, b.pet, b.area_km2, *[p[k] for k in ["maxbas", "tthres", "dd", "fc", "beta", "pwp", "k0", "k1", "k2", "kp", "lthres", "snow0", "s0", "w01", "w02"]])[0] * 86.4 / b.area_km2


def _milc(b, p):
    from lumod.models.milc_model import _milc
    return _milc(b.precipitation, b.pet, b.area_km2, *[p[k] for k in ["gamma", "w0", "wmax", "alpha", "m", "ks", "nu"]], .2)[0] * 86.4 / b.area_km2


def _registry():
    # LuMod imports install broad warning filters. Restore the caller's filters.
    with warnings.catch_warnings():
        from lumod import models
    definitions = [
        ("GR4J", "daily", models.GR4J, _gr4j, {"x1": (100, 1500), "x2": (-5, 5), "x3": (10, 500), "x4": (.5, 10)}, "LuMod 0.1.3.0 GR4J", False),
        ("GR2M", "monthly", models.GR2M, _gr2m, {"x1": (50, 2000), "x2": (.1, 2)}, "LuMod 0.1.3.0 GR2M", False),
        ("GR1A", "annual", models.GR1A, _gr1a, {"x": (.1, 5)}, "LuMod 0.1.3.0 GR1A", False),
        ("HYMOD", "daily", models.HYMOD, _hymod, {"wmax": (50, 2000), "alpha": (.01, .99), "beta": (.01, 1.99), "cexp": (.01, 1.99), "ks": (.001, .2), "kq": (.05, .95), "kmax": (.1, 1), "llet": (0, .95)}, "LuMod modified HYMOD2 (Roy et al. 2017), not classic five-parameter HYMOD", False),
        ("HBV", "daily", models.HBV, _hbv, {"maxbas": (1.1, 7), "tthres": (-3, 5), "dd": (.1, 10), "fc": (50, 1500), "beta": (.1, 6), "pwp": (.1, 1), "k0": (.01, .9), "k1": (.001, .5), "k2": (.0001, .1), "kp": (.001, .2), "lthres": (0, 150)}, "LuMod modified HBV-light with temperature-index snow", True),
        ("MILC", "daily", models.MILC, _milc, {"gamma": (.5, 15), "wmax": (50, 2000), "alpha": (.1, 5), "m": (1, 20), "ks": (1, 300), "nu": (.01, .99)}, "LuMod single-layer MISDc/MILC; upstream routing dt=0.2", False),
    ]
    registry = {name: Model(name, step, dict(cls().params), bounds, runner, variant, temp) for name, step, cls, runner, bounds, variant, temp in definitions}
    from .extended_models import extended_registry
    registry.update(extended_registry())
    from .marrmot import marrmot_registry
    registry.update(marrmot_registry())
    return registry


MODELS = None


def get_model(name: str | Model) -> Model:
    global MODELS
    if isinstance(name, Model):
        return name
    if MODELS is None:
        MODELS = _registry()
    try:
        return MODELS[name.upper()]
    except KeyError:
        raise ValueError(f"Unknown model {name!r}. Available: {', '.join(MODELS)}") from None


def list_models(*, include_optional=False):
    get_model("GR4J")
    return [{"name": m.name, "timestep": m.timestep, "variant": m.variant, "backend": m.backend, "runtime_requirement": "octave-cli + Octave optim" if m.backend == "octave" else "installed Python dependencies", "calibrated_parameters": list(m.bounds), "defaults": dict(m.defaults), "bounds": dict(m.bounds)} for m in MODELS.values() if include_optional or m.backend != "octave"]
