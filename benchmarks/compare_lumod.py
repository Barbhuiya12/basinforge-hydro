"""Real LuMod bundled example; compares equal warm simulation workloads only."""
import argparse
import json
import platform
import time
from importlib.metadata import version

import numpy as np

from basinforge import Basin, get_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=50)
    parser.add_argument("--model", choices=["GR4J", "HYMOD", "HBV", "MILC"], default="GR4J")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    import lumod
    from lumod import models
    info, frame = lumod.load_example(2)
    # Explicit PET: compute once through the original public API, not per candidate.
    upstream = getattr(models, args.model)(area=float(info.area), lat=float(info.lat))
    outputs = upstream.run(frame)
    frame = frame.copy()
    if "pet" not in frame:
        if "pet" not in outputs:
            raise RuntimeError("Upstream example has no PET for this model.")
        frame["pet"] = outputs.pet
    basin = Basin.from_frame(frame, basin_id="lumod-example-2", area_km2=float(info.area), latitude=float(info.lat), columns={"prec": "precipitation", "qt": "qobs", "tmean": "temperature"}, q_unit="m3/s")
    model = get_model(args.model)
    adapter = model.simulate(basin)
    baseline = upstream.run(frame).qt.to_numpy() * 86.4 / basin.area_km2
    np.testing.assert_allclose(adapter, baseline, rtol=2e-6, atol=2e-6)
    timings = {}
    for label, run in [("lumod_public_api", lambda: upstream.run(frame)), ("basinforge_array_adapter", lambda: model.simulate(basin))]:
        samples = []
        for _ in range(args.repeats):
            start = time.perf_counter()
            run()
            samples.append(time.perf_counter() - start)
        timings[label] = float(np.median(samples))
    print(json.dumps({"platform": platform.platform(), "python": platform.python_version(), "lumod": version("lumod"), "model": args.model, "time_steps": len(frame), "repeats": args.repeats, "numba_warm": True, "dataset": "LuMod bundled example 2; observations/forcing not generated", "median_seconds": timings, "public_api_over_adapter_ratio": timings["lumod_public_api"] / timings["basinforge_array_adapter"], "scope": "Simulation wrapper overhead only; same hydrological kernels; no calibration or universal speedup claim."}, indent=2))


if __name__ == "__main__":
    main()
