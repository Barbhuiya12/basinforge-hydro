"""One-call fit, global sensitivity and portable report workflow."""
import json
import os
from pathlib import Path
import shutil
import tempfile

from .analysis import calibrate_multistart
from .calibration import CalibrationConfig, calibrate
from .report import export_report
from .sensitivity import morris_sensitivity, sobol_sensitivity


def run_experiment(
    basin,
    model="GR4J",
    config=None,
    *,
    sensitivity="morris",
    sensitivity_options=None,
    output=None,
    starts=1,
    seeds=None,
):
    """Fit, analyze parameter sensitivity and optionally export a complete study.

    ``sensitivity`` is ``"morris"``, ``"sobol"`` or ``None``. Sensitivity
    uses the calibration bounds (and fixed parameters) and scores only the
    chronological training segment after warmup. The validation record is
    reserved for fit evaluation and never enters the sensitivity indices.
    If ``output`` is given, fit, HTML/PNG report and sensitivity JSON are
    staged and published as one new directory; existing output is refused.
    """
    config = config or CalibrationConfig()
    if not isinstance(starts, int) or isinstance(starts, bool) or starts < 1:
        raise ValueError("starts must be a positive integer.")
    if sensitivity not in {None, "morris", "sobol"}:
        raise ValueError("sensitivity must be 'morris', 'sobol', or None.")
    sensitivity_options = dict(sensitivity_options or {})
    final = Path(output) if output is not None else None
    stage = None
    if final is not None:
        if final.exists():
            raise FileExistsError(f"Experiment output already exists: {final}")
        if not final.parent.is_dir():
            raise FileNotFoundError(f"Experiment parent directory does not exist: {final.parent}")
        stage = Path(tempfile.mkdtemp(prefix=f".{final.name}-", dir=final.parent))
    try:
        if starts == 1:
            fit = calibrate(basin, model, config)
            trials = [fit]
        else:
            seed_values = tuple(seeds) if seeds is not None else tuple(config.seed + i for i in range(starts))
            if len(seed_values) != starts:
                raise ValueError("Provide exactly one seed per requested start.")
            search = calibrate_multistart(basin, model, config, seeds=seed_values)
            fit, trials = search["best"], search["trials"]
        if sensitivity == "morris":
            sensitivity_result = morris_sensitivity(basin, model, config, **sensitivity_options)
        elif sensitivity == "sobol":
            sensitivity_result = sobol_sensitivity(basin, model, config, **sensitivity_options)
        else:
            sensitivity_result = None
        result = {"fit": fit, "trials": trials, "sensitivity": sensitivity_result, "output": final}
        if stage is not None:
            fit.export(stage / "fit")
            if starts > 1:
                with (stage / "multistart.json").open("x", encoding="utf-8") as stream:
                    json.dump({"seeds": list(seed_values), "losses": [trial.objective_loss for trial in trials], "selected_by": "minimum calibration objective loss"}, stream, indent=2, allow_nan=False)
            export_report(basin, fit, stage / "report", model=model)
            from .models import get_model
            resolved_model = get_model(model)
            if hasattr(resolved_model.runner, "accounting"):
                accounting = resolved_model.runner.accounting(basin, fit.parameters)
                accounting.daily.to_csv(stage / "water-balance.csv")
                # Long-format export retains user names without using them as paths.
                import pandas as pd
                if accounting.sectors:
                    pd.concat(accounting.sectors, names=["sector", "date"]).to_csv(stage / "water-sectors.csv")
                else:
                    pd.DataFrame(columns=["sector", "date"]).to_csv(stage / "water-sectors.csv", index=False)
                with (stage / "water-summary.json").open("x", encoding="utf-8") as stream:
                    json.dump(accounting.summary(), stream, indent=2, allow_nan=False)
            if sensitivity_result is not None:
                with (stage / "sensitivity.json").open("x", encoding="utf-8") as stream:
                    json.dump(sensitivity_result, stream, indent=2, allow_nan=False)
            # Rename within the same parent directory to publish a complete result atomically.
            os.rename(stage, final)
        return result
    except Exception:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        raise
