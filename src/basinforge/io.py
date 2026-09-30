import json
from pathlib import Path

import pandas as pd

from .data import Basin


def load_basins(manifest):
    """CSV manifest with one local time-series CSV per basin, paths relative to manifest."""
    manifest = Path(manifest).resolve()
    frame = pd.read_csv(manifest, dtype={"basin_id": str, "path": str})
    if not {"basin_id", "path", "area_km2"}.issubset(frame.columns):
        raise ValueError("Basin manifest needs basin_id, path, area_km2 columns.")
    if frame.basin_id.isna().any() or frame.basin_id.duplicated().any():
        raise ValueError("Basin IDs must be nonempty and unique.")
    basins = []
    for row in frame.to_dict("records"):
        def optional(name, default):
            value = row.get(name, default)
            return default if pd.isna(value) else value
        basins.append(Basin.from_csv(manifest.parent / row["path"], basin_id=row["basin_id"], area_km2=float(row["area_km2"]), latitude=float(optional("latitude", 0)), timestep=optional("timestep", "daily"), q_unit=optional("q_unit", "mm")))
    return basins


def summary_frame(batch):
    rows = []
    for identifier, result in batch["results"].items():
        row = {"basin_id": identifier, "model": result.model, "status": "converged" if result.converged else "budget_exhausted", "objective_loss": result.objective_loss, "evaluations": result.evaluations, "seconds": result.elapsed_seconds, "resumed": identifier in batch["resumed"]}
        row.update({"cal_" + key: value for key, value in result.calibration_metrics.items()})
        if result.validation_metrics:
            row.update({"val_" + key: value for key, value in result.validation_metrics.items()})
        rows.append(row)
    for identifier, error in batch["errors"].items():
        rows.append({"basin_id": identifier, "status": "error", "error": error})
    return pd.DataFrame(rows)
