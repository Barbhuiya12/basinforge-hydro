"""Generate the LuMod case study, fitted hydrographs and downloadable results.

Run from the repository root after installing .[reference]. The source dataset
stays with LuMod; this export contains derived simulations and provenance.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from basinforge import Basin, CalibrationConfig, calibrate, calibrate_multistart, export_report, morris_sensitivity, sobol_sensitivity, __version__


def load_example(number):
    import lumod
    info, frame = lumod.load_example(number)
    frame = frame.copy()
    frame["pet"] = lumod.models.GR4J(area=float(info.area), lat=float(info.lat)).run(frame).pet
    return Basin.from_frame(frame, basin_id=f"lumod-example-{number}", area_km2=float(info.area), latitude=float(info.lat), columns={"prec": "precipitation", "qt": "qobs", "tmean": "temperature"}, q_unit="m3/s")


def sensitivity_results(output):
    output = Path(output)
    basin = load_example(2)
    config = CalibrationConfig(warmup=365, calibration_fraction=0.7)
    results = [morris_sensitivity(basin, "GR4J", config, trajectories=20, seed=42), sobol_sensitivity(basin, "GR4J", config, samples=1024, seed=42)]
    for name, result in zip(("morris", "sobol"), results):
        (output / f"sensitivity-{name}.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    figure = Figure(figsize=(11, 4), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(1, 2)
    items = results[0]["parameters"]
    axes[0].bar([i["parameter"] for i in items], [i["mu_star"] for i in items], color="#087e8b")
    axes[0].set(title="Morris screening · 20 trajectories", ylabel="Mean absolute normalized effect on NSE loss")
    items = results[1]["parameters"]
    positions = np.arange(len(items))
    axes[1].bar(positions - 0.18, [i["first_order"] for i in items], width=0.36, label="First order", color="#087e8b")
    axes[1].bar(positions + 0.18, [i["total_order"] for i in items], width=0.36, label="Total order", color="#9656a8")
    axes[1].set(xticks=positions, xticklabels=[i["parameter"] for i in items], title="Sobol · 1,024 base samples", ylabel="Variance fraction of NSE loss")
    axes[1].legend()
    figure.savefig(output / "example-2-sensitivity.png", dpi=160)


def run(output, *, maxiter=100, samples=3000, popsize=10):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows, parameters = [], []
    labels = {"de": "Differential evolution", "lhs": "Latin hypercube", "multistart": "Multi-start differential evolution"}
    for number in (1, 2, 3):
        basin = load_example(number)
        config = CalibrationConfig(warmup=365, calibration_fraction=0.7, maxiter=maxiter, popsize=popsize, samples=samples, seed=42)
        cut = int(len(basin.dates) * config.calibration_fraction)
        runs = {}
        for method in labels:
            trials = None
            if method == "multistart":
                search = calibrate_multistart(basin, "GR4J", config, seeds=(42, 43, 44))
                fit = search["best"]
                trials = search["trials"]
            else:
                fit = calibrate(basin, "GR4J", replace(config, method=method))
            runs[method] = fit
            folder = output / f"example-{number}" / method
            fit.export(folder)
            export_report(basin, fit, folder / "report")
            if trials:
                (folder / "trials.json").write_text(json.dumps([x.metadata() for x in trials], indent=2, allow_nan=False))
            row = {"example": number, "method": method, "label": labels[method], "steps": len(basin.dates), "area_km2": basin.area_km2, "calibration_start": str(basin.dates[365].date()), "calibration_end": str(basin.dates[cut - 1].date()), "validation_start": str(basin.dates[cut].date()), "validation_end": str(basin.dates[-1].date()), "seed": fit.config["seed"], "objective_loss": fit.objective_loss, "evaluations": sum(t.evaluations for t in trials) if trials else fit.evaluations, "seconds": sum(t.elapsed_seconds for t in trials) if trials else fit.elapsed_seconds, "converged": fit.converged}
            row.update({f"calibration_{k}": v for k, v in fit.calibration_metrics.items()})
            row.update({f"validation_{k}": v for k, v in fit.validation_metrics.items()})
            rows.append(row)
            parameters.append({"example": number, "method": method, **fit.parameters})
            print(json.dumps(row, allow_nan=False), flush=True)
        observed = basin.to_m3s(basin.qobs)
        figure = Figure(figsize=(12, 9), layout="constrained")
        FigureCanvasAgg(figure)
        axes = figure.subplots(3, 1)
        colors = {"de": "#087e8b", "lhs": "#d07800", "multistart": "#9656a8"}
        for ax, method in zip(axes, labels):
            fit = runs[method]
            ax.plot(basin.dates, observed, color="#334155", linewidth=0.6, alpha=0.65, label="Observed")
            ax.plot(basin.dates, basin.to_m3s(fit.simulated), color=colors[method], linewidth=0.6, label="Simulated")
            ax.axvspan(basin.dates[0], basin.dates[364], color="#94a3b8", alpha=0.2, label="Warmup")
            ax.axvspan(basin.dates[cut], basin.dates[-1], color="#34d399", alpha=0.15, label="Validation")
            ax.set(ylabel="Discharge (m³/s)", title=f"{labels[method]} · calibration NSE {fit.calibration_metrics['nse']:.3f} · validation NSE {fit.validation_metrics['nse']:.3f}")
            ax.legend(ncol=4, fontsize=8)
        figure.suptitle(f"LuMod example {number} · GR4J calibration and validation")
        figure.savefig(output / f"example-{number}-hydrographs.png", dpi=160)
        figure = Figure(figsize=(12, 5), layout="constrained")
        FigureCanvasAgg(figure)
        ax = figure.subplots()
        end = min(cut + 365, len(basin.dates))
        ax.plot(basin.dates[cut:end], observed[cut:end], color="#334155", lw=1.1, label="Observed")
        for method, fit in runs.items():
            ax.plot(basin.dates[cut:end], basin.to_m3s(fit.simulated)[cut:end], lw=0.9, color=colors[method], label=labels[method])
        ax.set(ylabel="Discharge (m³/s)", title=f"LuMod example {number} · first validation year")
        ax.legend(fontsize=8)
        figure.savefig(output / f"example-{number}-validation.png", dpi=160)
    pd.DataFrame(rows).to_csv(output / "metrics.csv", index=False)
    pd.DataFrame(parameters).to_csv(output / "parameters.csv", index=False)
    provenance = {"basinforge_version": __version__, "dataset": "LuMod 0.1.3.0 load_example(1), load_example(2), load_example(3)", "pet": "LuMod GR4J default PET routine using example latitude", "observed_discharge_source_unit": "m3/s", "model": "GR4J", "objective": "nse", "warmup_steps": 365, "calibration_fraction": 0.7, "maxiter": maxiter, "popsize": popsize, "lhs_samples": samples, "seeds": [42, 43, 44], "selection": "minimum training loss; validation never selects candidates or seeds"}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2))
    sensitivity_results(output)
    checksums = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob("*") if p.is_file()}
    (output / "checksums.json").write_text(json.dumps(checksums, indent=2))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("docs/site/case-study-results"))
    parser.add_argument("--maxiter", type=int, default=100)
    parser.add_argument("--samples", type=int, default=3000)
    parser.add_argument("--popsize", type=int, default=10)
    args = parser.parse_args()
    run(args.output, maxiter=args.maxiter, samples=args.samples, popsize=args.popsize)
