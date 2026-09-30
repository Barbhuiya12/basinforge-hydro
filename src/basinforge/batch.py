import hashlib
import json
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from .calibration import CalibrationConfig, CalibrationResult, calibrate, fingerprint
from .models import get_model


def _folder(basin, model):
    label = re.sub(r"[^a-zA-Z0-9_-]", "_", basin.basin_id)[:60] or "basin"
    return f"{label}-{hashlib.sha256(basin.basin_id.encode()).hexdigest()[:8]}-{model.name}"


def _job(basin, model, config, output, resume):
    directory = Path(output) / _folder(basin, model) if output else None
    if directory and directory.exists():
        if not resume:
            raise FileExistsError(f"Result already exists: {directory}; choose --resume or another output.")
        metadata = json.loads((directory / "fit.json").read_text())
        if metadata["fingerprint"] != fingerprint(basin, model, config):
            raise ValueError("Existing result has different data/configuration; choose another output folder.")
        simulation = pd.read_csv(directory / "simulation.csv")
        dates = pd.DatetimeIndex(pd.to_datetime(simulation["date"])).as_unit("ns")
        if not dates.equals(basin.dates) or not np.all(np.isfinite(simulation["qsim_mm"])):
            raise ValueError("Saved simulation is incomplete or incompatible.")
        return CalibrationResult(**metadata, dates=dates, simulated=simulation["qsim_mm"].to_numpy()), True
    result = calibrate(basin, model, config)
    if directory:
        result.export(directory)
    return result, False


def calibrate_many(basins, model="GR4J", config=None, *, workers=1, output=None, resume=False, fail_fast=False, progress=None):
    """Independent basin fits; errors isolated, successful completed jobs reusable."""
    basins = list(basins)
    if not basins or len({b.basin_id for b in basins}) != len(basins):
        raise ValueError("Basins must be nonempty with unique IDs.")
    if not isinstance(workers, int) or workers < 1:
        raise ValueError("workers must be a positive integer.")
    model = get_model(model)
    config = config or CalibrationConfig()
    results, errors, resumed = {}, {}, []

    def record(basin, call):
        try:
            result, reused = call()
            results[basin.basin_id] = result
            if reused:
                resumed.append(basin.basin_id)
        except Exception as exc:
            if fail_fast:
                raise
            errors[basin.basin_id] = f"{type(exc).__name__}: {exc}"
        if progress:
            progress({"completed": len(results) + len(errors), "total": len(basins), "basin_id": basin.basin_id})

    if workers == 1:
        for basin in basins:
            record(basin, lambda b=basin: _job(b, model, config, output, resume))
    else:
        import multiprocessing
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            futures = {pool.submit(_job, basin, model, config, output, resume): basin for basin in basins}
            for future in as_completed(futures):
                record(futures[future], future.result)
    return {"results": {key: results[key] for key in sorted(results)}, "errors": errors, "resumed": sorted(resumed)}


def compare_models(basins, models, config=None, **kwargs):
    basins = list(basins)
    comparisons = {}
    for name in models:
        model = get_model(name)
        compatible = [b for b in basins if b.timestep == model.timestep]
        if not compatible:
            comparisons[model.name] = {"results": {}, "errors": {"_model": f"No basins at {model.timestep} time step"}, "resumed": []}
        else:
            comparisons[model.name] = calibrate_many(compatible, model, config, **kwargs)
    return comparisons
