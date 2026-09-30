"""Reproducible robustness checks; no posterior uncertainty claims."""
from dataclasses import replace

import numpy as np

from .calibration import CalibrationConfig, calibrate
from .models import get_model


def calibrate_multistart(basin, model="GR4J", config=None, *, seeds=(42, 43, 44), progress=None):
    """Repeat independent searches; select by training loss, never validation."""
    config = config or CalibrationConfig()
    seeds = list(seeds)
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Provide a nonempty set of distinct seeds.")
    trials = []
    for seed in seeds:
        trial = calibrate(basin, model, replace(config, seed=seed))
        trials.append(trial)
        if progress:
            progress({"completed": len(trials), "total": len(seeds), "seed": seed, "loss": trial.objective_loss})
    return {"best": min(trials, key=lambda result: result.objective_loss), "trials": trials, "selection": "minimum calibration objective loss; validation not used"}


def simulate_ensemble(basin, model, parameter_sets, *, quantiles=(0.05, 0.5, 0.95)):
    """Descriptive parameter-scenario spread, not a calibrated posterior."""
    model = get_model(model)
    parameter_sets = list(parameter_sets)
    quantiles = np.asarray(quantiles, dtype=float)
    if not parameter_sets:
        raise ValueError("Provide at least one parameter set.")
    if quantiles.ndim != 1 or not len(quantiles) or not np.all(np.isfinite(quantiles)) or np.any((quantiles < 0) | (quantiles > 1)):
        raise ValueError("Quantiles must be finite probabilities in [0, 1].")
    simulations = np.stack([model.simulate(basin, params) for params in parameter_sets])
    return {"model": model.name, "dates": basin.dates, "simulations_mm": simulations, "quantile_probabilities": quantiles, "quantiles_mm": np.quantile(simulations, quantiles, axis=0), "interpretation": "parameter scenarios, not posterior or predictive confidence intervals"}
