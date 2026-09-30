# Model calibration

## Single basin

```python
from basinforge import Basin, CalibrationConfig, calibrate

basin = Basin.from_csv("basin.csv", basin_id="A", area_km2=1200, q_unit="m3/s")
config = CalibrationConfig(
    warmup=365, calibration_fraction=0.7,
    objective="nse", seed=42, maxiter=100,
)
fit = calibrate(basin, "GR4J", config)
print(fit.parameters)
print(fit.calibration_metrics)
print(fit.validation_metrics)
fit.export("results/A")
```

The first 70% of the record trains the model; the remaining 30% validates it. Warmup is excluded from training metrics. Model history continues through the validation boundary without resetting stores/routing.

Alternatively set `calibration_end="2015-12-31"` and optionally `validation_start="2016-01-01"`. Choose a fraction **or** a calibration end date, not both. Splits are chronological, never random.

## Search methods

| Method | Configuration | Interpretation |
| --- | --- | --- |
| Differential evolution | `method="de", maxiter=100, popsize=10` | Iterative population search |
| Latin hypercube | `method="lhs", samples=1000` | Fixed candidate budget; no convergence test |

Neither method guarantees a global optimum or a satisfactory fit. SCE-UA, DREAM/MCMC and Pareto optimization are not currently implemented.

## Objectives

Supported objectives include NSE, KGE (2009), RMSE and `log_nse`, defined as NSE of `log1p(Q)`. Weighted dictionaries produce a scalarized objective, not a Pareto front.

```python
config = CalibrationConfig(
    objective={"nse": 0.7, "log_nse": 0.3},
    warmup=365, calibration_fraction=0.7,
)
```

Mixed RMSE/dimensionless objectives require deliberate scaling. Constant observations reject undefined NSE/KGE. Missing observations are masked, not fabricated.

## Bounds and fixed parameters

```python
config = CalibrationConfig(
    warmup=365, calibration_fraction=0.7,
    bounds={"x1": [100, 1200], "x2": [-3, 3]},
    fixed={"ps0": 0.5},
)
```

`bounds` replaces the calibrated subset; omitted parameters retain their defaults. All ranges must stay within the implementation's supported bounds. Generic defaults/ranges are not basin-specific priors. MARRMoT `p01...` follow exact source order, not shared parameter meanings across models.

## Multi-start fitting

```python
from basinforge import calibrate_multistart

search = calibrate_multistart(basin, "GR4J", config, seeds=(42, 43, 44))
best = search["best"]
```

The minimum **training objective loss** selects the best fit. Validation is not used to choose a seed. Searches across seeds currently run serially.

## Command line

```bash
basinforge calibrate basin.csv --area 1200 --q-unit m3/s \
  --model GR4J --warmup 365 --calibration-fraction 0.7 \
  --starts 3 --report --output results/A
```

Use `--config settings.json` for other `CalibrationConfig` fields. Fit exports and reports refuse existing directories.
