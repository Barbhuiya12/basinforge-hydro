"""Fit real records bundled with LuMod; no invented observations or downloads."""
import argparse
import json
from pathlib import Path

from basinforge import Basin, CalibrationConfig, calibrate_many
from basinforge.io import summary_frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--maxiter", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("results/lumod-real-fraction"))
    args = parser.parse_args()
    import lumod
    basins = []
    for number in [1, 2, 3]:
        info, forcing = lumod.load_example(number)
        upstream = lumod.models.GR4J(area=float(info.area), lat=float(info.lat))
        pet = upstream.run(forcing).pet.to_numpy()
        frame = forcing.copy()
        frame["pet"] = pet
        basins.append(Basin.from_frame(frame, basin_id=f"lumod-example-{number}", area_km2=float(info.area), latitude=float(info.lat), columns={"prec": "precipitation", "qt": "qobs", "tmean": "temperature"}, q_unit="m3/s"))
    # Different records have different calendar years. Split each chronologically,
    # not randomly; warmup is excluded from the first 70% training segment.
    config = CalibrationConfig(warmup=365, calibration_fraction=0.7, maxiter=args.maxiter, popsize=6, seed=42)
    batch = calibrate_many(basins, "GR4J", config, workers=args.workers, output=args.output, resume=True, progress=lambda event: print(json.dumps(event), flush=True))
    print(summary_frame(batch).to_csv(index=False))
    if batch["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
