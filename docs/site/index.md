# Welcome to BasinForge’s documentation!

BasinForge is an open-source Python package for running and calibrating lumped hydrological models for **one basin or multiple basins**. These pages are intended for teaching, study and reproducible research.

The package provides 14 Python model implementations and 47 optional MARRMoT structures through Octave. Model names, variants, time steps and parameter bounds are documented separately.

Start with the [Quick Start](quickstart.md), browse the [model reference](models/index.md), follow the [tutorials](tutorials.md), or inspect the [Python API](api.md). Source code is available on [GitHub](https://github.com/Barbhuiya12/basinforge-hydro).

:::{note}
These are 61 selectable implementations/structures, not 61 distinct original model families or every published lumped model. MARRMoT structures resemble, but are not identical to, their original namesakes.
:::

## Key features

- Daily, monthly and annual model contracts with explicit units.
- Independent or shared-parameter multi-basin calibration.
- Differential evolution, Latin-hypercube sampling and multi-start fitting.
- Morris screening and Sobol first/total order global sensitivity.
- One-call calibration, training-only sensitivity and report exports.
- Chronological training/validation with continuous model history.
- NSE, KGE (2009), RMSE and explicitly defined log NSE.
- Saved parameters, simulations, hydrograph/flow-duration reports and scenario ensembles.
- Model source attribution, reference tests and stated scientific limitations.

## Quick installation

```bash
git clone https://github.com/Barbhuiya12/basinforge-hydro.git
cd basinforge-hydro
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
basinforge models
```

Windows activation: `.venv\Scripts\activate`. Python 3.11 or later is required. The package is not yet published to PyPI. See [Installation](installation.md) for Octave and development setup.

## Basic example

```python
from basinforge import Basin, CalibrationConfig, calibrate, get_model

basin = Basin.from_csv(
    "basin.csv", basin_id="my-basin", area_km2=1200,
    q_unit="m3/s", timestep="daily",
)
config = CalibrationConfig(
    warmup=365, calibration_fraction=0.7,
    objective="nse", seed=42, maxiter=100,
)
fit = calibrate(basin, "GR4J", config)
print(fit.parameters)
print(fit.calibration_metrics, fit.validation_metrics)
q_mm = get_model("GR4J").simulate(basin, fit.parameters)
fit.export("results/my-basin")
```

The file and basin area above illustrate the API; supply your actual records and metadata. [Input data](data.md) explains the CSV schema. [Real-record examples](examples.md) use observed catchment records bundled with LuMod.

## Where to start

| Task | Documentation |
| --- | --- |
| Prepare rainfall, PET and discharge | [Input data](data.md) |
| Choose a model | [Models](models/index.md) |
| Fit a single basin | [Calibration](calibration.md) |
| Fit several basins | [Multi-basin workflows](multi-basin.md) |
| Analyze global parameter sensitivity | [Sensitivity guide](calibration.md#sensitivity-analysis) |
| Review model equations | [Equation reference](equations.md) |
| Understand the measured results | [Verification study](study.md) |
| Find function signatures | [API reference](api.md) |

## Scientific use and attribution

Adapter/reference tests establish implementation consistency, not predictive performance for your basin. Parameter-scenario spread is not a calibrated uncertainty interval. The current evidence and numerical limitations are documented in the [verification study](study.md).

BasinForge is maintained by [Barbhuiya12](https://github.com/Barbhuiya12), independently of the upstream model authors. Cite the actual model implementation and scientific papers, not just this workflow package. [Sources and licenses](credits.md) identify LuMod, hydromodel, SMARTpy, MARRMoT and the ABCD equations. The project is GPL-3.0-only.
