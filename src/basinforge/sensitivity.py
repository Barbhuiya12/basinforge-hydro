"""Training-period global sensitivity for scalar hydrology objectives.

Parameter samples are generated in a unit hypercube and linearly scaled to
the declared calibration bounds. Observations after the calibration cutoff
never enter the score. Failed simulations stop the analysis rather than
silently distorting variance-based indices.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import qmc

from .calibration import CalibrationConfig, _parameter_space, _period
from .metrics import loss
from .models import get_model


def _problem(basin, model, config, bounds):
    model = get_model(model)
    model.validate_basin(basin)
    training, _ = _period(basin, config)
    parameter_defaults, names, calibration_bounds = _parameter_space(model, config)
    if bounds is not None:
        selected = dict(bounds)
        if set(selected) != set(names):
            raise ValueError(f"Sensitivity bounds must specify every free calibrated parameter: {names}.")
        _, _, calibration_bounds = _parameter_space(model, CalibrationConfig(**{**vars(config), "bounds": selected}))
    pairs = list(zip(names, calibration_bounds))
    model.simulate(training)

    def evaluate(unit_parameters, label):
        parameters = dict(parameter_defaults)
        for (name, (low, high)), fraction in zip(pairs, unit_parameters):
            parameters[name] = float(low + fraction * (high - low))
        simulated = np.asarray(model.runner(training, parameters), dtype=np.float64)
        if simulated.shape != training.precipitation.shape or not np.all(np.isfinite(simulated)) or np.any(simulated < 0):
            raise RuntimeError(f"Sensitivity simulation {label} returned invalid discharge; narrow the parameter bounds.")
        score = loss(training.qobs[config.warmup:], simulated[config.warmup:], config.objective)
        if not np.isfinite(score):
            raise RuntimeError(f"Sensitivity simulation {label} returned a non-finite objective.")
        return float(score)

    return model, pairs, evaluate


def morris_sensitivity(basin, model="GR4J", config=None, *, trajectories=12, levels=4, seed=42, bounds=None):
    """Morris screening using normalized elementary effects.

    Evaluations = trajectories * (free parameters + 1). ``mu_star`` is the
    mean absolute effect on the minimized configured training objective per
    unit change across a parameter's declared range. ``sigma`` describes
    effect variability and can indicate nonlinearity or interactions.
    """
    config = config or CalibrationConfig()
    if not isinstance(trajectories, int) or trajectories < 2:
        raise ValueError("trajectories must be an integer of at least 2.")
    if not isinstance(levels, int) or levels < 4 or levels % 2:
        raise ValueError("levels must be an even integer of at least 4.")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer.")
    model, pairs, evaluate = _problem(basin, model, config, bounds)
    dimension = len(pairs)
    step = levels / (2 * (levels - 1))
    grid = np.arange(levels) / (levels - 1)
    rng = np.random.default_rng(seed)
    effects = {name: [] for name, _ in pairs}
    for trajectory in range(trajectories):
        # Select a legal grid origin, randomized direction and coordinate order.
        origin = rng.choice(grid[grid <= 1 - step + 1e-12], size=dimension)
        directions = rng.choice(np.array([-1.0, 1.0]), size=dimension)
        current = origin + (directions < 0) * step
        score = evaluate(current, f"Morris trajectory {trajectory + 1}, start")
        for parameter_index in rng.permutation(dimension):
            following = current.copy()
            following[parameter_index] += directions[parameter_index] * step
            next_score = evaluate(following, f"Morris trajectory {trajectory + 1}, step {parameter_index + 1}")
            name = pairs[parameter_index][0]
            effects[name].append((next_score - score) / (directions[parameter_index] * step))
            current, score = following, next_score
    rows = []
    for name, interval in pairs:
        values = np.asarray(effects[name])
        rows.append({"parameter": name, "bounds": [float(v) for v in interval], "mu": float(np.mean(values)), "mu_star": float(np.mean(np.abs(values))), "sigma": float(np.std(values, ddof=1)), "effects": values.tolist()})
    rows.sort(key=lambda item: item["mu_star"], reverse=True)
    training, _ = _period(basin, config)
    return {"method": "morris", "model": model.name, "variant": model.variant, "objective": config.objective, "score_period": "training data after warmup only", "training_steps": len(training.dates) - config.warmup, "seed": seed, "levels": levels, "trajectories": trajectories, "evaluations": trajectories * (dimension + 1), "parameters": rows, "interpretation": "Normalized Morris effects on the minimized training objective. mu_star ranks influence within the reported bounds; sigma indicates effect variability, including possible interaction and nonlinearity."}


def sobol_sensitivity(basin, model="GR4J", config=None, *, samples=256, seed=42, bounds=None, bootstrap=200):
    """Saltelli/Jansen Sobol indices from a scrambled Sobol digital net.

    ``samples`` must be a power of two (minimum four). Runtime is
    ``samples * (parameters + 2)`` model simulations. Bootstrap intervals
    quantify sampling variability of the index estimators, not hydrologic
    predictive uncertainty.
    """
    config = config or CalibrationConfig()
    if not isinstance(samples, int) or samples < 4 or samples & (samples - 1):
        raise ValueError("samples must be a power of two and at least 4.")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer.")
    if not isinstance(bootstrap, int) or bootstrap < 0:
        raise ValueError("bootstrap must be a nonnegative integer.")
    model, pairs, evaluate = _problem(basin, model, config, bounds)
    dimension = len(pairs)
    unit = qmc.Sobol(d=2 * dimension, scramble=True, seed=seed).random_base2(int(np.log2(samples)))
    a, b = unit[:, :dimension], unit[:, dimension:]
    ya = np.empty(samples)
    yb = np.empty(samples)
    y_ab = np.empty((dimension, samples))
    for i in range(samples):
        ya[i] = evaluate(a[i], f"Sobol A sample {i + 1}")
        yb[i] = evaluate(b[i], f"Sobol B sample {i + 1}")
    for j, (name, _) in enumerate(pairs):
        hybrid = a.copy()
        hybrid[:, j] = b[:, j]
        for i in range(samples):
            y_ab[j, i] = evaluate(hybrid[i], f"Sobol AB[{name}] sample {i + 1}")
    variance = float(np.var(np.concatenate((ya, yb)), ddof=1))
    if not np.isfinite(variance) or variance <= np.finfo(float).eps * max(1.0, float(np.mean(np.square(np.concatenate((ya, yb)))))):
        raise ValueError("Sobol indices are undefined because the sampled objective has negligible variance.")
    first = 1 - np.mean((yb[None, :] - y_ab) ** 2, axis=1) / (2 * variance)
    total = np.mean((ya[None, :] - y_ab) ** 2, axis=1) / (2 * variance)
    intervals = np.full((dimension, 4), np.nan)
    if bootstrap:
        rng = np.random.default_rng(seed + 1)
        boot_first = np.empty((bootstrap, dimension))
        boot_total = np.empty((bootstrap, dimension))
        for replicate in range(bootstrap):
            index = rng.integers(0, samples, size=samples)
            local_variance = float(np.var(np.concatenate((ya[index], yb[index])), ddof=1))
            if local_variance <= 0:
                boot_first[replicate] = np.nan
                boot_total[replicate] = np.nan
            else:
                boot_first[replicate] = 1 - np.mean((yb[index][None, :] - y_ab[:, index]) ** 2, axis=1) / (2 * local_variance)
                boot_total[replicate] = np.mean((ya[index][None, :] - y_ab[:, index]) ** 2, axis=1) / (2 * local_variance)
        intervals[:, 0:2] = np.nanpercentile(boot_first, [2.5, 97.5], axis=0).T
        intervals[:, 2:4] = np.nanpercentile(boot_total, [2.5, 97.5], axis=0).T
    rows = []
    for j, (name, interval) in enumerate(pairs):
        rows.append({"parameter": name, "bounds": [float(v) for v in interval], "first_order": float(first[j]), "first_order_ci95": [float(x) if np.isfinite(x) else None for x in intervals[j, :2]], "total_order": float(total[j]), "total_order_ci95": [float(x) if np.isfinite(x) else None for x in intervals[j, 2:]], "first_order_estimator": "1 - mean((f(B) - f(A_Bi))^2) / (2 Var(Y))", "total_order_estimator": "mean((f(A) - f(A_Bi))^2) / (2 Var(Y))"})
    rows.sort(key=lambda item: item["total_order"], reverse=True)
    return {"method": "sobol_jansen", "model": model.name, "variant": model.variant, "objective": config.objective, "score_period": "training data after warmup only", "seed": seed, "base_samples": samples, "bootstrap_replicates": bootstrap, "evaluations": samples * (dimension + 2), "parameters": rows, "interpretation": "Variance-based global effects over the reported independent parameter bounds. Finite-sample first-order estimates may be negative or sum above one. Bootstrap intervals describe index sampling variability, not predictive uncertainty."}
