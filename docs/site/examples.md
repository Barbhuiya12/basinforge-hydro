# Examples and case studies

Start with the [LuMod case study](case-study.md), which compares all supported calibration searches on three example catchments, with hydrographs, sensitivity analyses, parameters and downloadable results.

To reproduce the case study from a checkout, install `pip install -e '.[reference]'` to access the LuMod example datasets and PET routine. The Python model kernels themselves run with BasinForge's core dependencies.

## Three-basin calibration

From the repository root:

```bash
python examples/real_lumod_basins.py --workers 2 --maxiter 100
```

This uses three LuMod catchment records, its GR4J PET routine, explicit observed-discharge conversion, 365 daily warmup steps and a chronological 70/30 split. Example 1 performed poorly in the recorded experiment; do not interpret optimizer convergence as proof of predictive skill.

## Compare daily implementations

```bash
python examples/compare_real_models.py \
  --models GR4J GR5J HYMOD_CLASSIC XAJ --samples 20 \
  --output results/real-model-comparison
```

For the optional Octave engine, add `MARRMOT_29` to `--models` after installing Octave + optim. Small sample budgets demonstrate execution, not effective full-model calibration. The example saves fit metadata, simulations and static reports.

## Hydrograph and flow-duration reports

```python
from basinforge import export_report
export_report(basin, fit, "results/A-report")
```

The report checks that the basin/model/config match the fitted result. It contains train/validation metrics and whole-record flow-duration curves using matched finite observations after warmup. Existing output directories are refused.

## Parameter-scenario ensemble

```python
from basinforge import calibrate_multistart, simulate_ensemble

search = calibrate_multistart(basin, "GR4J", config, seeds=(42, 43, 44))
ensemble = simulate_ensemble(
    basin, "GR4J", [fit.parameters for fit in search["trials"]],
)
```

Quantiles describe the supplied parameter scenarios. They are not posterior samples or predictive confidence intervals.

## Simulation microbenchmark

```bash
python benchmarks/compare_lumod.py
```

This compares wrapper overhead for warmed GR4J runs on LuMod example 2. See [the measured workload](study.md).
