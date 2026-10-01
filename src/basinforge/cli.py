import argparse
import json
from dataclasses import replace
from pathlib import Path

from . import Basin, CalibrationConfig, calibrate, calibrate_many, compare_models, get_model, list_models, configure_marrmot, check_marrmot, calibrate_multistart, export_report, run_experiment
from .io import load_basins, summary_frame


def main():
    parser = argparse.ArgumentParser(description="BasinForge: lumped models, explicit units, reproducible calibration.")
    commands = parser.add_subparsers(dest="command", required=True)
    models_command = commands.add_parser("models", help="List Python adapters; --all also lists optional Octave adapters")
    models_command.add_argument("--all", action="store_true", help="Include 47 optional MARRMoT structures")
    doctor = commands.add_parser("doctor", help="Check Python versions and optional MARRMoT runtime")
    doctor.add_argument("--check-marrmot", action="store_true")
    doctor.add_argument("--octave")
    doctor.add_argument("--octave-package-list")
    for name in ["run", "calibrate", "experiment", "batch", "compare"]:
        child = commands.add_parser(name)
        child.add_argument("input", type=Path, help="Time-series CSV, or basin manifest for batch/compare")
        child.add_argument("--output", type=Path, required=True)
        child.add_argument("--model", default="GR4J")
        child.add_argument("--octave", help="Path to optional octave-cli executable")
        child.add_argument("--octave-package-list", help="Optional Octave local package-list file")
        if name in {"run", "calibrate", "experiment"}:
            child.add_argument("--basin-id", default="basin")
            child.add_argument("--area", type=float, required=True, help="Area in km²")
            child.add_argument("--latitude", type=float, default=0)
            child.add_argument("--timestep", choices=["daily", "monthly", "annual"], default="daily")
            child.add_argument("--q-unit", choices=["mm", "m3/s"], default="mm")
        if name == "run":
            child.add_argument("--parameters", type=Path, help="JSON parameter dictionary or fit.json")
        else:
            child.add_argument("--config", type=Path, help="JSON CalibrationConfig")
            child.add_argument("--warmup", type=int)
            child.add_argument("--calibration-end")
            child.add_argument("--calibration-fraction", type=float)
            child.add_argument("--validation-start")
            child.add_argument("--maxiter", type=int)
            child.add_argument("--seed", type=int)
        if name in {"batch", "compare"}:
            child.add_argument("--workers", type=int, default=1)
            child.add_argument("--resume", action="store_true")
        if name == "compare":
            child.add_argument("--models", nargs="+", default=["GR4J", "HYMOD", "HBV", "MILC"])
        if name == "calibrate":
            child.add_argument("--starts", type=int, default=1, help="Independent seeds; select by training loss")
            child.add_argument("--report", action="store_true", help="Export hydrograph/flow-duration HTML report")
        if name == "experiment":
            child.add_argument("--starts", type=int, default=1, help="Independent fits; select by training loss")
            child.add_argument("--sensitivity", choices=["morris", "sobol", "none"], default="morris")
            child.add_argument("--trajectories", type=int, default=12, help="Morris trajectory count")
            child.add_argument("--samples", type=int, default=256, help="Sobol power-of-two base sample count")
    args = parser.parse_args()
    if args.command == "models":
        print(json.dumps(list_models(include_optional=args.all), indent=2))
        return
    try:
        if args.command == "doctor":
            import platform
            from importlib.metadata import version
            result = {"python": platform.python_version(), "basinforge": __import__("basinforge").__version__, "packages": {name: version(name) for name in ["numpy", "pandas", "scipy", "numba"]}, "python_adapters": len(list_models()), "optional_octave_adapters": 47}
            if args.check_marrmot:
                description = check_marrmot(octave=args.octave, package_list=args.octave_package_list)
                result["marrmot"] = {"status": "all classes instantiated; simulation not checked by doctor", "classes": len(description["models"]), "octave": description["octave_version"]}
            print(json.dumps(result, indent=2))
            return
        if args.octave or args.octave_package_list:
            configure_marrmot(octave=args.octave, package_list=args.octave_package_list)
        if args.command in {"run", "calibrate", "experiment"}:
            basin = Basin.from_csv(args.input, basin_id=args.basin_id, area_km2=args.area, latitude=args.latitude, timestep=args.timestep, q_unit=args.q_unit)
        if args.command == "run":
            import pandas as pd
            params = json.loads(args.parameters.read_text()) if args.parameters else None
            if params and "parameters" in params:
                params = params["parameters"]
            simulation = get_model(args.model).simulate(basin, params)
            with args.output.open("x", encoding="utf-8", newline="") as stream:
                pd.DataFrame({"date": basin.dates, "qsim_mm": simulation, "qsim_m3s": basin.to_m3s(simulation)}).to_csv(stream, index=False)
            print(f"Simulated {len(simulation)} {basin.timestep} steps → {args.output}")
            return
        config = CalibrationConfig(**json.loads(args.config.read_text())) if args.config else CalibrationConfig()
        overrides = {key: getattr(args, key) for key in ["warmup", "calibration_end", "calibration_fraction", "validation_start", "maxiter", "seed"] if getattr(args, key) is not None}
        config = replace(config, **overrides)
        if args.command == "experiment":
            selected = None if args.sensitivity == "none" else args.sensitivity
            settings = {"trajectories": args.trajectories} if selected == "morris" else {"samples": args.samples} if selected == "sobol" else {}
            study = run_experiment(basin, args.model, config, sensitivity=selected, sensitivity_options=settings, output=args.output, starts=args.starts)
            print(json.dumps({"output": str(args.output), "model": study["fit"].model, "parameters": study["fit"].parameters, "validation_metrics": study["fit"].validation_metrics, "sensitivity": study["sensitivity"]}, indent=2, allow_nan=False))
            return
        if args.command == "calibrate":
            if args.starts < 1:
                raise ValueError("--starts must be a positive integer.")
            if args.starts == 1:
                result = calibrate(basin, args.model, config, progress=lambda event: print(json.dumps(event), flush=True))
                trial_metadata = None
            else:
                searches = calibrate_multistart(basin, args.model, config, seeds=range(config.seed, config.seed + args.starts), progress=lambda event: print(json.dumps(event), flush=True))
                result = searches["best"]
                trial_metadata = {"selection": searches["selection"], "trials": [fit.metadata() for fit in searches["trials"]]}
            result.export(args.output)
            if trial_metadata:
                (args.output / "multistart.json").write_text(json.dumps(trial_metadata, indent=2, allow_nan=False), encoding="utf-8")
            if args.report:
                print(f"Report: {export_report(basin, result, args.output / 'report')}")
            print(json.dumps(result.metadata(), indent=2))
            return
        basins = load_basins(args.input)
        options = dict(workers=args.workers, output=args.output, resume=args.resume, progress=lambda event: print(json.dumps(event), flush=True))
        if args.command == "batch":
            batch = calibrate_many(basins, args.model, config, **options)
            print(summary_frame(batch).to_csv(index=False))
            if batch["errors"]:
                raise SystemExit(1)
        else:
            batches = compare_models(basins, args.models, config, **options)
            for model, batch in batches.items():
                print(f"Model: {model}")
                print(summary_frame(batch).to_csv(index=False))
            if any(batch["errors"] for batch in batches.values()):
                raise SystemExit(1)
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
