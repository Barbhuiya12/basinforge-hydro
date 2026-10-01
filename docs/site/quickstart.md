# Quick Start

This guide takes you from installation to your first calibrated model. Python 3.11 or later is required. The 14 Python models run without Octave; the 47 optional MARRMoT structures require it.

1. Follow [Installation](installation.md) and run `basinforge doctor`.
2. Prepare your rainfall, potential evaporation and observed discharge using the [data requirements](data.md).
3. Follow the [single-basin calibration guide](calibration.md). Choose the warmup and chronological training/validation split explicitly.
4. Inspect the validation metrics and simulated hydrograph before interpreting a fitted parameter set.

## One Python call for calibration

```python
from basinforge import Basin, CalibrationConfig, calibrate

basin = Basin.from_csv(
    "basin.csv", basin_id="A", area_km2=1200,
    q_unit="m3/s", timestep="daily",
)
fit = calibrate(basin, "GR4J", CalibrationConfig(
    warmup=365, calibration_fraction=0.7, seed=42,
))
print(fit.validation_metrics)
fit.export("results/A")
```

Replace the file and area with your own catchment metadata. `calibrate` runs the optimizer and computes training/validation metrics; it does not automatically choose scientifically appropriate data, settings or validation periods.

:::{note}
Sensitivity analysis and a verified Python-only port of every optional model are ongoing work, not released capabilities. See the [roadmap](roadmap.md).
:::
