"""Saved, non-interactive hydrograph/flow-duration diagnostics."""
import html
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .calibration import CalibrationConfig, fingerprint
from .models import get_model


def export_report(basin, fit, directory):
    """Create a static HTML/PNG report; never overwrite an existing directory."""
    config = CalibrationConfig(**fit.config)
    if fingerprint(basin, get_model(fit.model), config) != fit.fingerprint:
        raise ValueError("Basin/model/config does not match the fitted result.")
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(f"Report already exists: {directory}")
    # Avoid pyplot/global backend changes in caller applications.
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    figure = Figure(figsize=(12, 7), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(2, 1)
    discharge = basin.to_m3s(fit.simulated)
    observed = basin.to_m3s(basin.qobs) if basin.qobs is not None else None
    axes[0].plot(basin.dates, discharge, color="#0e7490", lw=1, label="Simulated")
    if observed is not None:
        axes[0].plot(basin.dates, observed, color="#334155", lw=0.7, alpha=0.6, label="Observed")
    axes[0].set(ylabel="Discharge (m³/s)", title=f"{basin.basin_id} · {fit.model}")
    if config.warmup:
        axes[0].axvspan(basin.dates[0], basin.dates[min(config.warmup, len(basin.dates)) - 1], color="#94a3b8", alpha=0.2, label="Warmup")
    if config.calibration_end or config.calibration_fraction is not None:
        end = int(basin.dates.searchsorted(config.calibration_end, side="right")) if config.calibration_end else int(len(basin.dates) * config.calibration_fraction)
        if end < len(basin.dates):
            start = max(basin.dates[end], pd.Timestamp(config.validation_start)) if config.validation_start else basin.dates[end]
            axes[0].axvspan(start, basin.dates[-1], color="#34d399", alpha=0.12, label="Validation")
    axes[0].legend(loc="upper right")
    # FDC uses matched, observed days after warmup; not all simulation days
    # against a shorter observed series with missing values.
    keep = np.arange(len(discharge)) >= config.warmup
    if observed is not None:
        keep &= np.isfinite(observed)
    selected = discharge[keep]
    if len(selected):
        exceedance = 100 * np.arange(1, len(selected) + 1) / (len(selected) + 1)
        axes[1].plot(exceedance, np.sort(selected)[::-1], label="Simulated", color="#0e7490")
        if observed is not None:
            axes[1].plot(exceedance, np.sort(observed[keep])[::-1], label="Observed", color="#334155")
    axes[1].set(xlabel="Exceedance probability (%)", ylabel="Discharge (m³/s)", title="Whole-record flow duration · matched observations · after warmup")
    axes[1].legend()
    directory.mkdir(parents=True, exist_ok=False)
    figure.savefig(directory / "diagnostics.png", dpi=150)
    (directory / "summary.json").write_text(json.dumps(fit.metadata(), indent=2, allow_nan=False), encoding="utf-8")
    title = html.escape(f"{basin.basin_id} / {fit.model}")
    rows = []
    for period, metrics in [("Calibration", fit.calibration_metrics), ("Validation", fit.validation_metrics)]:
        if metrics:
            for name, value in metrics.items():
                formatted = "undefined" if value is None else f"{value:.5g}"
                rows.append(f"<tr><td>{period}</td><td>{html.escape(name)}</td><td>{formatted}</td></tr>")
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#0f172a;background:#f8fafc}}img{{width:100%;border-radius:12px}}table{{border-collapse:collapse;background:white}}td,th{{padding:10px 24px;text-align:left;border-bottom:1px solid #e2e8f0}}small{{color:#475569}}</style>
<h1>{title}</h1><p>{html.escape(fit.variant)}</p><img src="diagnostics.png" alt="Hydrograph and flow-duration diagnostics"><h2>Performance</h2>
<table><tr><th>Period</th><th>Metric</th><th>Value</th></tr>{''.join(rows)}</table><p>Optimizer convergence: {fit.converged}. Evaluations: {fit.evaluations}.</p>
<small>Convergence does not prove a global optimum or an acceptable hydrological fit. Validation is chronological. This report is not a predictive uncertainty assessment.</small></html>"""
    (directory / "index.html").write_text(document, encoding="utf-8")
    return directory / "index.html"
