# Multi-basin workflows

## Independent parameter vectors

```python
from basinforge import CalibrationConfig, calibrate_many
from basinforge.io import load_basins, summary_frame

config = CalibrationConfig(warmup=365, calibration_fraction=0.7, seed=42)

if __name__ == "__main__":
    basins = load_basins("basins.csv")
    batch = calibrate_many(
        basins, "GR4J", config,
        workers=4, output="results", resume=True,
    )
    print(summary_frame(batch))
    print(batch["errors"])
```

Each basin fits its own parameter vector. Processes use spawn, so protect application entry points with `if __name__ == "__main__":`, especially on macOS/Windows. Tiny jobs can be slower in parallel because of process/JIT startup.

## Shared parameter vector

```python
from basinforge import calibrate_shared

shared = calibrate_shared(basins, "GR4J", config)
print(shared["parameters"])
```

One common vector is fitted with equal basin weights by default. Each basin retains its own forcing/state trajectory. This is not attribute-based parameter regionalization and does not prove transferability to ungauged basins.

## Compare implementations

```python
from basinforge import compare_models

comparison = compare_models(
    basins, ["GR4J", "HYMOD_CLASSIC", "XAJ"],
    config, workers=4,
)
```

Choose compatible time steps and fair forcing/validation contracts. Model names alone do not imply identical equations, initial states or parameter meanings.

## Resume and failure handling

`resume=True` reuses completed jobs after checking data/config fingerprints. It does not resume a partially completed optimizer. Errors are isolated per basin unless fail-fast is requested. Changed/incompatible outputs are not overwritten.

## Command line

```bash
basinforge batch basins.csv --model GR4J --workers 4 --output results --resume
basinforge compare basins.csv --models GR4J HYMOD_CLASSIC XAJ \
  --workers 4 --output results --resume
```
