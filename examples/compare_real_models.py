"""Compare daily adapters on actual LuMod-bundled observations.

Small LHS budgets demonstrate execution, not production-quality fitting.
Include MARRMOT_29 to exercise Octave (external runtime required).
"""
import argparse
import json
from pathlib import Path

from basinforge import Basin, CalibrationConfig, compare_models, export_report
from basinforge.io import summary_frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["GR4J", "GR5J", "HYMOD_CLASSIC", "XAJ"])
    parser.add_argument("--record", type=int, choices=[1, 2, 3], default=2)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("results/real-model-comparison"))
    args = parser.parse_args()
    import lumod
    info, forcing = lumod.load_example(args.record)
    reference = lumod.models.GR4J(area=float(info.area), lat=float(info.lat))
    forcing = forcing.copy()
    forcing["pet"] = reference.run(forcing).pet.to_numpy()
    basin = Basin.from_frame(forcing, basin_id=f"lumod-example-{args.record}", area_km2=float(info.area), latitude=float(info.lat), columns={"prec": "precipitation", "qt": "qobs", "tmean": "temperature"}, q_unit="m3/s")
    config = CalibrationConfig(method="lhs", samples=args.samples, warmup=365, calibration_fraction=.7, seed=42)
    print(json.dumps({"observations": "LuMod bundled catchment record, not synthetic", "days": len(basin.dates), "selection": "training loss only", "warning": "small search budget; no production skill claim"}), flush=True)
    batches = compare_models([basin], args.models, config, output=args.output, resume=True)
    failures = {}
    for name, batch in batches.items():
        print(name, flush=True)
        print(summary_frame(batch).to_csv(index=False), flush=True)
        failures.update({name + ":" + key: value for key, value in batch["errors"].items()})
        for fit in batch["results"].values():
            report = args.output / name / basin.basin_id / "report"
            if not report.exists():
                export_report(basin, fit, report)
    if failures:
        print(json.dumps(failures, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
