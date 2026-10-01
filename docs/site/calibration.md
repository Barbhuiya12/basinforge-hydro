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

## Sensitivity analysis

`morris_sensitivity` screens parameters using elementary effects. It reports signed mean effect (`mu`), mean absolute effect (`mu_star`) and effect spread (`sigma`), normalized to each parameter's declared range. `sobol_sensitivity` reports first-order and total-order variance fractions using Jansen estimators. Sobol base sample counts must be powers of two; the model evaluation budget is `samples × (free parameters + 2)`. First-order estimates can be negative from finite sampling.

Both analyses use the configured calibration bounds and score only training observations after warmup. They rerun models with fresh initial states, use independent uniform parameter samples, and do not report posterior or predictive uncertainty. Narrow bounds explicitly if the full supported model range is scientifically inappropriate. More details: [equation definitions](equations.md).

```python
from basinforge import morris_sensitivity, sobol_sensitivity

morris = morris_sensitivity(basin, "GR4J", config, trajectories=20, seed=42)
sobol = sobol_sensitivity(basin, "GR4J", config, samples=256, seed=42)
```

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

For fitting, sensitivity analysis and reports in one call, use `run_experiment`:

```python
from basinforge import run_experiment

study = run_experiment(
    basin, "GR4J", config,
    sensitivity="morris",
    sensitivity_options={"trajectories": 20, "seed": 42},
    output="results/A-study",
)
print(study["fit"].validation_metrics)
print(study["sensitivity"]["parameters"][:3])
```

`output` refuses existing paths and publishes fit parameters/simulation, a hydrograph report and `sensitivity.json` together.

The equivalent single-basin CLI is `basinforge experiment basin.csv --area 1200 --q-unit m3/s --model GR4J --warmup 365 --calibration-fraction 0.7 --sensitivity morris --trajectories 20 --output results/A-study`. Choose `--sensitivity sobol --samples 256` for variance-based analysis (`--samples` must be a power of two), or `--sensitivity none` to export only the fit and diagnostics.

## Command line

```bash
basinforge calibrate basin.csv --area 1200 --q-unit m3/s \
  --model GR4J --warmup 365 --calibration-fraction 0.7 \
  --starts 3 --report --output results/A
```

Use `--config settings.json` for other `CalibrationConfig` fields. Fit exports and reports refuse existing directories.
