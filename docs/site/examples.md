# Examples with real observations

These examples use catchment records distributed with LuMod. They do not fabricate discharge observations. Data/implementation provenance and numerical conditions are described in the [verification study](study.md).

Running BasinForge's Python models does not require LuMod or SMARTpy. Install the optional `reference` extra (`pip install 'basinforge-hydro[reference]'`) only if you want the independent upstream parity tests.

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

This compares wrapper overhead for warmed GR4J runs on one real record. It does not show a universal speedup or faster Octave fitting. See [the measured workload](study.md).
