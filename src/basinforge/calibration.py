from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution
from scipy.stats import qmc

from .data import Basin
from .metrics import evaluate, loss
from .models import Model, get_model


@dataclass(frozen=True)
class CalibrationConfig:
    method: str = "de"
    objective: str | dict = "nse"
    warmup: int = 365
    calibration_end: str | None = None
    calibration_fraction: float | None = None
    validation_start: str | None = None
    seed: int = 42
    maxiter: int = 100
    popsize: int = 10
    samples: int = 1000
    polish: bool = False
    bounds: dict | None = None
    fixed: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.method not in {"de", "lhs"}:
            raise ValueError("method must be de (differential evolution) or lhs (Latin hypercube search).")
        for name in ["warmup", "seed", "maxiter", "popsize", "samples"]:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < (1 if name in {"popsize", "samples"} else 0):
                raise ValueError(f"Invalid {name}.")
        if self.calibration_fraction is not None:
            if isinstance(self.calibration_fraction, bool) or not np.isfinite(self.calibration_fraction) or not 0 < self.calibration_fraction < 1:
                raise ValueError("calibration_fraction must be between 0 and 1, exclusive.")
            if self.calibration_end is not None:
                raise ValueError("Choose calibration_fraction or calibration_end, not both.")
        if self.validation_start and not self.calibration_end and self.calibration_fraction is None:
            raise ValueError("validation_start requires calibration_end or calibration_fraction.")


@dataclass
class CalibrationResult:
    basin_id: str
    model: str
    variant: str
    parameters: dict
    objective_loss: float
    calibration_metrics: dict
    validation_metrics: dict | None
    evaluations: int
    elapsed_seconds: float
    converged: bool
    message: str
    dates: pd.DatetimeIndex
    simulated: np.ndarray
    history: list
    fingerprint: str
    config: dict

    def metadata(self):
        return {k: v for k, v in vars(self).items() if k not in {"dates", "simulated"}}

    def export(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        # No source files or prior results are overwritten.
        with (directory / "fit.json").open("x", encoding="utf-8") as stream:
            json.dump(self.metadata(), stream, indent=2, allow_nan=False)
        pd.DataFrame({"date": self.dates, "qsim_mm": self.simulated}).to_csv(directory / "simulation.csv", index=False)


def fingerprint(basin, model, config):
    from dataclasses import asdict
    digest = hashlib.sha256(json.dumps({"basin_id": basin.basin_id, "area": basin.area_km2, "latitude": basin.latitude, "timestep": basin.timestep, "model": model.name, "variant": model.variant, "defaults": model.defaults, "config": asdict(config)}, sort_keys=True, allow_nan=False).encode())
    digest.update(basin.dates.asi8.tobytes())
    if hasattr(model.runner, "fingerprint"):
        digest.update(model.runner.fingerprint().encode())
    for values in [basin.precipitation, basin.pet, basin.qobs, basin.temperature]:
        digest.update(b"None" if values is None else values.tobytes())
    return digest.hexdigest()


def _period(basin, config):
    if basin.qobs is None:
        raise ValueError(f"{basin.basin_id}: calibration requires observed discharge.")
    end = len(basin.dates)
    if config.calibration_end:
        end = int(basin.dates.searchsorted(pd.Timestamp(config.calibration_end), side="right"))
    elif config.calibration_fraction is not None:
        end = int(len(basin.dates) * config.calibration_fraction)
    if end <= config.warmup + 1:
        raise ValueError("Calibration period needs at least two steps after warmup.")
    from dataclasses import replace
    training = replace(basin, dates=basin.dates[:end], precipitation=basin.precipitation[:end], pet=basin.pet[:end], qobs=basin.qobs[:end], temperature=basin.temperature[:end] if basin.temperature is not None else None)
    validation = np.arange(len(basin.dates)) >= end
    if config.validation_start:
        start = pd.Timestamp(config.validation_start)
        if start <= basin.dates[end - 1]:
            raise ValueError("Validation must start after calibration, not overlap it.")
        validation &= basin.dates >= start
        if not np.any(validation):
            raise ValueError("Requested validation period has no data.")
    # Validate objective before launching a costly search; zeros expose undefined metrics.
    loss(training.qobs[config.warmup:], np.zeros(end - config.warmup), config.objective)
    return training, validation


def _parameter_space(model, config):
    fixed = model.parameters(config.fixed)
    bounds = dict(model.bounds if config.bounds is None else config.bounds)
    if set(bounds) - set(model.bounds):
        raise ValueError("Calibration bounds must name supported calibrated parameters.")
    for key, value in bounds.items():
        if len(value) != 2 or not np.all(np.isfinite(value)) or value[0] >= value[1]:
            raise ValueError(f"Invalid bounds for {key}.")
        low, high = model.bounds[key]
        if not low <= value[0] < value[1] <= high:
            raise ValueError(f"Bounds for {key} must lie inside [{low}, {high}].")
    for key in config.fixed:
        bounds.pop(key, None)
    if not bounds:
        raise ValueError("At least one unfixed parameter must be calibrated.")
    return fixed, list(bounds), list(bounds.values())


def _search(function, bounds, config, history, progress):
    if config.method == "de":
        def callback(intermediate_result):
            event = {"generation": int(intermediate_result.nit), "loss": float(intermediate_result.fun)}
            history.append(event)
            if progress:
                progress(event)
        result = differential_evolution(function, bounds, rng=config.seed, maxiter=config.maxiter, popsize=config.popsize, polish=config.polish, updating="deferred", callback=callback)
        return result.x, float(result.fun), int(result.nfev), bool(result.success), str(result.message)
    sampler = qmc.LatinHypercube(d=len(bounds), seed=config.seed)
    population = qmc.scale(sampler.random(config.samples), np.array(bounds)[:, 0], np.array(bounds)[:, 1])
    best_x, best_loss = population[0], float("inf")
    for i, candidate in enumerate(population):
        value = function(candidate)
        if value < best_loss:
            best_x, best_loss = candidate.copy(), value
        if (i + 1) % max(1, config.samples // 20) == 0:
            event = {"evaluation": i + 1, "loss": float(best_loss)}
            history.append(event)
            if progress:
                progress(event)
    return best_x, float(best_loss), config.samples, False, "Latin hypercube sample budget exhausted; no convergence test."


def calibrate(basin: Basin, model: str | Model = "GR4J", config: CalibrationConfig | None = None, *, progress=None) -> CalibrationResult:
    from dataclasses import asdict
    config = config or CalibrationConfig()
    model = get_model(model)
    model.validate_basin(basin)
    training, validation = _period(basin, config)
    baseline, names, bounds = _parameter_space(model, config)
    # Fail early on engine/Numba compatibility problems; never hide them as bad scores.
    model.simulate(training)
    start = time.perf_counter()

    def function(candidate):
        parameters = dict(baseline, **dict(zip(names, map(float, candidate))))
        simulated = np.asarray(model.runner(training, parameters))
        if not np.all(np.isfinite(simulated)) or np.any(simulated < 0):
            return 1e30
        return loss(training.qobs[config.warmup:], simulated[config.warmup:], config.objective)

    history = []
    candidate, best_loss, evaluations, converged, message = _search(function, bounds, config, history, progress)
    if not np.isfinite(best_loss) or best_loss >= 1e30:
        raise RuntimeError("All parameter evaluations failed; no fit was produced.")
    parameters = dict(baseline, **dict(zip(names, map(float, candidate))))
    training_q = model.simulate(training, parameters)
    # Full uninterrupted run preserves routing/storage through validation; no reset.
    simulated = model.simulate(basin, parameters)
    validation_metrics = evaluate(basin.qobs[validation], simulated[validation]) if np.count_nonzero(np.isfinite(basin.qobs[validation])) >= 2 else None
    return CalibrationResult(basin.basin_id, model.name, model.variant, parameters, best_loss, evaluate(training.qobs[config.warmup:], training_q[config.warmup:]), validation_metrics, evaluations, time.perf_counter() - start, converged, message, basin.dates, simulated, history, fingerprint(basin, model, config), asdict(config))


def calibrate_shared(basins, model="GR4J", config=None, *, basin_weights=None):
    """One common parameter vector; equal basin weighting, not pooled hydrographs."""
    config = config or CalibrationConfig()
    model = get_model(model)
    basins = list(basins)
    if not basins or len({b.basin_id for b in basins}) != len(basins):
        raise ValueError("Provide a nonempty collection with unique basin IDs.")
    weights = np.ones(len(basins)) if basin_weights is None else np.asarray(basin_weights, dtype=float)
    if weights.shape != (len(basins),) or not np.all(np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError("Basin weights must be positive and match the basin count.")
    baseline, names, bounds = _parameter_space(model, config)
    periods = []
    for basin in basins:
        model.validate_basin(basin)
        training, validation = _period(basin, config)
        model.simulate(training)
        periods.append((training, validation))
    start = time.perf_counter()

    def function(candidate):
        params = dict(baseline, **dict(zip(names, map(float, candidate))))
        values = []
        for training, _ in periods:
            simulated = np.asarray(model.runner(training, params))
            if not np.all(np.isfinite(simulated)) or np.any(simulated < 0):
                return 1e30
            values.append(loss(training.qobs[config.warmup:], simulated[config.warmup:], config.objective))
        return float(np.average(values, weights=weights))

    history = []
    candidate, best, evaluations, converged, message = _search(function, bounds, config, history, None)
    if not np.isfinite(best) or best >= 1e30:
        raise RuntimeError("All shared parameter evaluations failed.")
    params = dict(baseline, **dict(zip(names, map(float, candidate))))
    diagnostics = {}
    for basin, (training, validation) in zip(basins, periods):
        sim = model.simulate(basin, params)
        diagnostics[basin.basin_id] = {"calibration": evaluate(training.qobs[config.warmup:], model.simulate(training, params)[config.warmup:]), "validation": evaluate(basin.qobs[validation], sim[validation]) if np.count_nonzero(np.isfinite(basin.qobs[validation])) >= 2 else None, "simulated": sim}
    return {"model": model.name, "variant": model.variant, "parameters": params, "objective_loss": best, "evaluations": evaluations, "elapsed_seconds": time.perf_counter() - start, "converged": converged, "message": message, "history": history, "basins": diagnostics}
