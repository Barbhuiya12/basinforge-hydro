import numpy as np


def pairs(observed, simulated):
    observed, simulated = np.asarray(observed, dtype=float), np.asarray(simulated, dtype=float)
    if observed.shape != simulated.shape or observed.ndim != 1:
        raise ValueError("Metrics require equally shaped one-dimensional arrays.")
    keep = np.isfinite(observed)
    if not np.all(np.isfinite(simulated[keep])):
        raise ValueError("Simulation must be finite wherever an observation exists.")
    observed, simulated = observed[keep], simulated[keep]
    if len(observed) < 2:
        raise ValueError("At least two valid observations are required.")
    return observed, simulated


def nse(observed, simulated):
    o, s = pairs(observed, simulated)
    denominator = np.sum((o - np.mean(o)) ** 2)
    if denominator <= 0:
        raise ValueError("NSE is undefined for constant observations.")
    return float(1 - np.sum((s - o) ** 2) / denominator)


def kge(observed, simulated):
    """KGE 2009: Pearson r, standard-deviation ratio, mean ratio."""
    o, s = pairs(observed, simulated)
    if np.std(o) <= 0 or np.mean(o) <= 0:
        raise ValueError("KGE requires positive mean and nonconstant observations.")
    r = float(np.corrcoef(o, s)[0, 1]) if np.std(s) > 0 else 0.0
    return float(1 - np.sqrt((r - 1) ** 2 + (np.std(s) / np.std(o) - 1) ** 2 + (np.mean(s) / np.mean(o) - 1) ** 2))


def rmse(observed, simulated):
    o, s = pairs(observed, simulated)
    return float(np.sqrt(np.mean((s - o) ** 2)))


def log_nse(observed, simulated):
    o, s = pairs(observed, simulated)
    if np.any(o < 0) or np.any(s < 0):
        raise ValueError("log NSE requires nonnegative discharge.")
    return nse(np.log1p(o), np.log1p(s))


METRICS = {"nse": nse, "kge": kge, "rmse": rmse, "log_nse": log_nse}


def evaluate(observed, simulated):
    result = {}
    for name, function in METRICS.items():
        try:
            result[name] = function(observed, simulated)
        except ValueError:
            result[name] = None
    return result


def loss(observed, simulated, objective):
    weights = {objective: 1.0} if isinstance(objective, str) else dict(objective)
    if not weights or any(name not in METRICS or not np.isfinite(weight) or weight <= 0 for name, weight in weights.items()):
        raise ValueError("Objective must name nse/kge/rmse/log_nse or give positive finite weights.")
    total = 0.0
    for name, weight in weights.items():
        score = METRICS[name](observed, simulated)
        total += weight * (score if name == "rmse" else 1 - score)
    return total / sum(weights.values())
