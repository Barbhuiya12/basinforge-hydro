# BasinForge

Lumped hydrological simulation, calibration and sensitivity analysis for single and multiple catchments.

[![Python tests](https://github.com/Barbhuiya12/basinforge-hydro/actions/workflows/tests.yml/badge.svg)](https://github.com/Barbhuiya12/basinforge-hydro/actions/workflows/tests.yml)
[![Documentation](https://github.com/Barbhuiya12/basinforge-hydro/actions/workflows/pages.yml/badge.svg)](https://barbhuiya12.github.io/basinforge-hydro/)

[Documentation](https://barbhuiya12.github.io/basinforge-hydro/) · [Quick start](https://barbhuiya12.github.io/basinforge-hydro/quickstart.html) · [Case study](https://barbhuiya12.github.io/basinforge-hydro/case-study.html) · [Release 0.1.0](https://github.com/Barbhuiya12/basinforge-hydro/releases/tag/v0.1.0)

## Features

- 14 Python model implementations and 47 optional MARRMoT structures.
- Single-basin, parallel multi-basin and shared-parameter calibration.
- Differential evolution, Latin-hypercube search and multi-start fitting.
- Chronological calibration and validation with NSE, KGE, RMSE and log NSE.
- Morris and Sobol sensitivity analysis.
- Saved parameters, simulations, hydrographs and HTML reports.

The Python models include GR1A, GR2M, GR3J, GR4J, GR5J, GR6J, HYMOD, HYMOD_CLASSIC, HBV, MILC, XAJ, XAJ_MZ, SMART and ABCD. See the [model reference](https://barbhuiya12.github.io/basinforge-hydro/models/index.html) for each implementation's equations, parameters and time step. The optional MARRMoT structures require Octave and its `optim` package.

## Install

Requires Python 3.11 or later. Install the 0.1.0 release with pip:

```bash
python -m pip install https://github.com/Barbhuiya12/basinforge-hydro/releases/download/v0.1.0/basinforge_hydro-0.1.0-py3-none-any.whl
basinforge doctor
```

For an editable installation:

```bash
git clone https://github.com/Barbhuiya12/basinforge-hydro.git
cd basinforge-hydro
python -m pip install -e .
```

## Quick start

Calibrate GR4J, analyze parameter sensitivity and export a hydrograph report in one call:

```python
from basinforge import Basin, CalibrationConfig, run_experiment

basin = Basin.from_csv(
    "basin.csv",
    basin_id="A",
    area_km2=1200,
    q_unit="m3/s",
    timestep="daily",
)

study = run_experiment(
    basin,
    "GR4J",
    CalibrationConfig(warmup=365, calibration_fraction=0.7, seed=42),
    sensitivity="morris",
    output="study-A",
)

print(study["fit"].parameters)
print(study["fit"].validation_metrics)
```

Supply your own CSV and catchment area. Use `date, precipitation, pet, qobs` columns; temperature-dependent models also need `temperature`. Precipitation and PET are mm per model step. Set the observed discharge unit explicitly and choose a warmup appropriate to the model's time step. Output directories must be new.

The same workflow is available from the command line:

```bash
basinforge experiment basin.csv --area 1200 --q-unit m3/s \
  --model GR4J --warmup 365 --calibration-fraction 0.7 \
  --sensitivity morris --output study-A
```

See the [input guide](https://barbhuiya12.github.io/basinforge-hydro/data.html), [calibration guide](https://barbhuiya12.github.io/basinforge-hydro/calibration.html) and [multi-basin guide](https://barbhuiya12.github.io/basinforge-hydro/multi-basin.html) for other workflows.

## LuMod case study

The [case study](https://barbhuiya12.github.io/basinforge-hydro/case-study.html) compares all supported calibration searches on three LuMod example catchments. It includes calibration and validation scores, observed and simulated hydrographs, Morris/Sobol sensitivity plots, and downloadable parameters and simulations.

To reproduce it from a checkout:

```bash
python -m pip install -e '.[reference]'
python examples/lumod_case_study.py --output lumod-case-study
```

The case-study output directory must be new.

## License and credits

BasinForge is distributed under [GPL-3.0-only](LICENSE). It incorporates scientific implementations from LuMod, hydromodel, SMARTpy and MARRMoT with retained licenses and attribution. See [third-party credits](THIRD_PARTY.md) for sources and model citations.
