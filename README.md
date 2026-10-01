# BasinForge

**Lumped hydrological simulation and calibration across one basin or many.**

[![Python tests](https://github.com/Barbhuiya12/basinforge-hydro/actions/workflows/tests.yml/badge.svg)](https://github.com/Barbhuiya12/basinforge-hydro/actions/workflows/tests.yml)
[![Study site](https://github.com/Barbhuiya12/basinforge-hydro/actions/workflows/pages.yml/badge.svg)](https://barbhuiya12.github.io/basinforge-hydro/)

[Study & documentation](https://barbhuiya12.github.io/basinforge-hydro/) · [Model reference](https://barbhuiya12.github.io/basinforge-hydro/models/index.html) · [Measured results](https://barbhuiya12.github.io/basinforge-hydro/study.html) · [Source credits](THIRD_PARTY.md)

Version 0.2.0 integrates **14 Python models and all 47 optional MARRMoT structures**, with one simulation/calibration interface. Single-basin, process-parallel multi-basin, shared-parameter fitting, chronological validation, multi-start calibration, scenario ensembles and local HTML reports are included. These are 61 selectable implementations/structures, **not 61 distinct original model families or every model ever published**. See the broader [model research inventory](docs/MODEL_CATALOG.md) and [source attribution](THIRD_PARTY.md).

## Install

```sh
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/basinforge models
```

Python ≥3.11. A first run can take longer because LuMod's Numba kernels compile. Models are pinned because these fast adapters call upstream internal kernel functions.

For a fresh checkout, first run `git clone https://github.com/Barbhuiya12/basinforge-hydro.git` and `cd basinforge-hydro`. This package is not yet published to PyPI.

## Runnable models

| Model | Time step | Exact engine/variant |
| --- | --- | --- |
| GR4J | Daily | LuMod GR4J |
| HYMOD | Daily | LuMod modified HYMOD2; **not** classic five-parameter HYMOD |
| HBV | Daily | LuMod modified HBV-light; needs mean temperature |
| MILC | Daily | LuMod single-layer MISDc adaptation, upstream routing dt=0.2 |
| GR2M | Monthly | LuMod GR2M |
| GR1A | Annual | LuMod GR1A |
| GR3J, GR5J, GR6J | Daily | Pinned hydromodel implementations; not asserted equivalent to airGR |
| HYMOD_CLASSIC | Daily | hydromodel classic five-parameter HYMOD |
| XAJ, XAJ_MZ | Daily | hydromodel Xinanjiang and MZ routing variants |
| SMART | Daily | SMARTpy 0.2.2 Python engine; daily forcing split uniformly into 24 hourly steps |
| ABCD | Monthly | Thomas four-parameter water balance; explicit initial soil/groundwater stores |
| MARRMOT_01 … MARRMOT_47 | Daily | Optional Octave engine, pinned MARRMoT v2 structures; not original named models |

Upstream hydrological equations are retained. MARRMoT has one documented Octave method-handle compatibility patch and a per-simulation random seed for reproducible fallback solves. Parity checks compare the six LuMod adapters to its public API and six hydromodel kernels plus all 47 MARRMoT structures to independent upstream simulations. SMART has a separate hourly reference check; ABCD has independent equation/conservation checks. This verifies implementation consistency, not field skill or equivalence to other engines. Parameter midpoints and empty/part-filled initial stores are starting defaults, not recommended basin calibrations.

## Optional 47-model Octave backend

Install Octave and its `optim` package separately. On Ubuntu/Debian: `sudo apt install octave octave-optim`. Other systems can use their Octave distribution and `pkg install -forge optim` (which may need a compiler/dependencies). The package contains scientific source files, **not an Octave executable**.

```sh
basinforge models --all
basinforge doctor --check-marrmot
basinforge calibrate basin.csv --area 1200 --model MARRMOT_29 \
  --warmup 365 --calibration-fraction 0.7 --output results/marrmot-hymod
```

For a nonstandard runtime, use `--octave /path/to/octave-cli` and optionally `--octave-package-list /path/to/local-package-list`, or the environment variables `BASINFORGE_OCTAVE` and `BASINFORGE_OCTAVE_PACKAGE_LIST`. Python callers can use `configure_marrmot(octave=..., package_list=..., timeout=300)`. Its settings survive spawned basin workers. Persistent workers cache each basin's forcing to reduce file/process overhead; the Octave solvers are **not claimed faster than LuMod's Numba kernels**.

MARRMoT parameters are `p01`, `p02`, … in the exact order of the corresponding bundled `.m` class, with source-derived bounds. Initial stores are `s01`, …, defaulting to zero and fixed unless explicitly changed. Inspect source comments before tuning them. Snow/temperature-dependent IDs are 06, 12, 30, 31, 32, 34, 35, 37, 41, 43, 44 and 45. `marrmot_details(basin, model, parameters)` exposes raw discharge, actual evaporation, stores, solver residuals and water-balance error. Runtime preflight checks constructors/dependencies, not hydrological validity for your data.

Upstream solvers can return invalid flow for some parameter/forcing combinations. For example, MARRMOT_33 produces about −1.6e-6 mm on the empty-store dry reference fixture. The public simulation API **rejects this**, rather than hiding it as zero; its raw output is retained for reference testing/diagnosis. All 47 calibration-interface tests use a separate wet fixture. Neither test promises successful fitting for arbitrary data or bounds.

## Single basin: Python

```python
from basinforge import Basin, CalibrationConfig, calibrate, get_model

basin = Basin.from_csv(
    "basin.csv", basin_id="Beas", area_km2=1200,
    q_unit="m3/s", timestep="daily",
)
config = CalibrationConfig(
    warmup=365,
    calibration_end="2015-12-31",
    validation_start="2016-01-01",
    objective="kge", seed=42, maxiter=100,
)
fit = calibrate(basin, "GR4J", config)
print(fit.parameters, fit.calibration_metrics, fit.validation_metrics)
fit.export("results/Beas")  # refuses to overwrite
q_mm = get_model("GR4J").simulate(basin, fit.parameters)
q_m3s = basin.to_m3s(q_mm)
```

Time-series CSV columns: `date,precipitation,pet,qobs,temperature`. P and PET must be nonnegative **mm per time step**. `qobs` is optional for simulation and required for calibration; its unit must be explicitly selected (`mm` per step or `m3/s`). Temperature is in °C and required for HBV. All forcing steps must be present and finite. Missing discharge observations may be NaN; missing forcing days must **not** be dropped or silently filled. Dates must be unique and increasing. Monthly/annual data are never automatically treated as daily data.

Column names can be mapped with `columns={"prec": "precipitation", "qt": "qobs", "tmean": "temperature"}` in `Basin.from_frame` / `from_csv`. Explicit PET is required; upstream PET-only parameters such as MILC `kc` and HBV `cevp` do not affect runs with supplied PET and are excluded from search.

## Multi-basin: Python

```python
from basinforge import calibrate_many, calibrate_shared, compare_models
from basinforge.io import load_basins, summary_frame

basins = load_basins("basins.csv")
batch = calibrate_many(
    basins, "GR4J", config,
    workers=4, output="results", resume=True,
)
print(summary_frame(batch))
shared = calibrate_shared(basins, "GR4J", config)  # one vector, equal basin weight
comparison = compare_models(basins, ["GR4J", "HYMOD"], config, workers=4)
```

For basins with different calendar coverage, use `CalibrationConfig(warmup=365, calibration_fraction=0.7)`: the first 70% of each record trains the model and the remaining 30% validates it. Splits are chronological, never random. Choose a fraction **or** `calibration_end`, not both. Warmup is a count of model steps: choose appropriate values for monthly/annual models instead of the daily default of 365.

Use `if __name__ == "__main__":` around process-parallel application entry points, especially on macOS/Windows. A shared fit is not parameter regionalization: it deliberately forces a common vector, including fixed initial fractions, while each basin has its own forcing/state trajectory.

`basins.csv` contains one row per basin, with time-series paths relative to the manifest:

```text
basin_id,path,area_km2,latitude,timestep,q_unit
Beas,data/beas.csv,1200,32,daily,m3/s
Ravi,data/ravi.csv,800,32,daily,m3/s
```

These rows illustrate a schema, **not bundled observations or verified basin areas**. Supply your actual records and basin metadata.

## CLI

```sh
basinforge run basin.csv --area 1200 --model GR4J --output simulation.csv
basinforge calibrate basin.csv --area 1200 --q-unit m3/s \
  --warmup 365 --calibration-end 2015-12-31 --output results/single
basinforge calibrate basin.csv --area 1200 --model GR6J \
  --warmup 365 --calibration-fraction 0.7 --starts 4 --report --output results/gr6j
basinforge batch basins.csv --model GR4J --workers 4 --output results --resume
basinforge compare basins.csv --models GR4J HYMOD HBV MILC \
  --workers 4 --output results --resume
```

`--config settings.json` accepts `CalibrationConfig` fields. Example:

```json
{"method":"de","objective":{"nse":0.7,"log_nse":0.3},"warmup":365,"seed":42,"maxiter":100,"popsize":10,"bounds":{"x1":[100,1200],"x2":[-3,3],"x3":[20,400],"x4":[1,8]},"fixed":{"ps0":0.5}}
```

Differential evolution or Latin-hypercube sampling are implemented. Weighted objectives are **scalarized**, not a Pareto-front optimizer. Mixed RMSE/dimensionless objectives need user-chosen scaling. `bounds` replaces the tunable subset; omitted parameters remain fixed at defaults. Ranges are conservative package search/safety choices, not universal hydrological priors. `nres` is fixed integer routing configuration, not a continuous fitted parameter. No SCE-UA/DREAM/MCMC or uncertainty posterior is claimed.

## Multi-start fits, scenario ensembles and reports

```python
from basinforge import calibrate_multistart, simulate_ensemble, export_report

search = calibrate_multistart(basin, "GR4J", config, seeds=(42, 43, 44))
best = search["best"]  # selected by training loss, never validation score
ensemble = simulate_ensemble(basin, "GR4J", [fit.parameters for fit in search["trials"]])
export_report(basin, best, "results/Beas-report")
```

Ensemble quantiles describe the supplied parameter scenarios; they are **not calibrated uncertainty intervals or posterior samples**. Reports contain hydrograph/flow-duration plots and train/validation metrics with no external JavaScript. Reports and fit exports refuse existing output directories. Multi-start fitting is currently serial across seeds; independent basins remain process-parallel.

## Reliability and performance

- Forcing arrays are prepared once; calibration calls compiled model kernels directly rather than creating Pandas outputs per candidate.
- Independent basins can run in separate spawned processes. No nested optimizer pools; process startup and repeated JIT compilation can make tiny jobs slower.
- Calibration uses only forcing/observations through the training cutoff. Validation runs a continuous full forcing history with fitted parameters; stores/routing are not reset at the boundary.
- Finite missing observations are masked consistently; constant observations reject undefined NSE/KGE. Invalid simulated discharge is never silently omitted.
- KGE is **2009** (standard-deviation ratio); log NSE is explicitly `NSE(log1p(Q))`.
- Results include parameters, objective, calibration/validation metrics, search trace, convergence flag, evaluation count, and simulation CSV.
- `resume=True` reuses **completed basin jobs**, checking data/config fingerprints. It does not resume a partially finished optimizer or guarantee recovery from a partially written output directory.
- Errors are isolated per basin in batch output. Changed data/config or existing incompatible results are never overwritten.
- The upstream MILC interpolation/routing conventions are retained; no new causality, conservation, or cross-engine equivalence claims are made. No model state hand-off/chunked forecast interface yet.

Benchmark using `python benchmarks/compare_lumod.py`; first-call compilation is excluded. Benchmarks use the real bundled LuMod example record. Report measured machine/model/workload results, not a universal “faster than LuMod” claim. Calibration/simulation tests also use controlled fixtures to check numerical behavior.

On this development machine (macOS ARM64, Python 3.14.3), a warmed GR4J run on the 3,287-step LuMod example-2 record measured median **0.571 ms** through LuMod's public API versus **0.220 ms** through this adapter over 20 repetitions: approximately **2.59× for this workload**. Both use the same compiled equations; this measures wrapper overhead, not a universal model/calibration speedup.

Run the real-data multi-basin example (no fabricated observations):

```sh
.venv/bin/python examples/real_lumod_basins.py --workers 2 --maxiter 100
```

It uses the three catchment records distributed by LuMod, computes PET with its existing routine, converts observed discharge explicitly, and saves fitted parameters and simulations. Low search budgets are demonstrations of execution, not guarantees of a good hydrological fit.

See [verification results and limitations](docs/VERIFICATION.md) for the actual three-basin fit scores and benchmark conditions.

## Extend

Create a `Model` with `defaults`, `bounds`, `timestep`, `variant`, and `runner(basin, parameters) -> discharge_mm_per_step`. Pass it to `calibrate`, `calibrate_many`, or `calibrate_shared`. The runner must be importable/pickleable for multiprocessing. This is the extension mechanism, not a claim that external models are already integrated.

## Research, attribution, and license

Primary sources: [LuMod documentation](https://zaul_ae.gitlab.io/lumod-docs/), [LuMod source](https://gitlab.com/Zaul_AE/lumod), [MARRMoT](https://github.com/wknoben/MARRMoT), [RavenPy model emulators](https://ravenpy.readthedocs.io/en/latest/notebooks/04_Emulating_hydrological_models.html), [hydromad](https://hydromad.github.io/reference/), [INRAE GR models](https://webgr.inrae.fr/eng/tools/hydrological-models), [SuperflexPy](https://superflexpy.readthedocs.io/en/latest/), [SciPy differential evolution](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html).

LuMod's model implementations are by **Saul Arciniega Esparza and collaborators**. BasinForge incorporates their numerical kernels with retained attribution and license; LuMod remains a dependency for real-record examples and reference tests. BasinForge is not affiliated with or an official successor to LuMod. GPL-3.0-only; see [LICENSE](LICENSE). Model sources and their scientific references must be credited in research.

Additional upstream projects: [hydromodel](https://github.com/OuyangWenyu/hydromodel), [SMARTpy](https://github.com/ThibHlln/smartpy), and [ABCD equations](https://abcd.walkerenvres.com/theory.html). Exact pinned revisions, retained licenses and modifications are in [THIRD_PARTY.md](THIRD_PARTY.md). Research-only families are explicitly separated from runnable adapters. See the [next additions and acceptance criteria](docs/ROADMAP.md).

## Build the study site locally

```sh
uv pip install --python .venv/bin/python -e '.[docs]'
.venv/bin/python scripts/build_site.py --output _site
.venv/bin/python -m http.server 8000 --directory _site
```

Open `http://localhost:8000`. The site uses Sphinx with the Read the Docs theme, following the study-friendly layout of NeuralHydrology: a collapsible sidebar, search, breadcrumbs, Quick Start, model reference, tutorials, configuration arguments and Python API documentation. Model parameters and API entries are generated from the package, while study results and source credits come from maintained Markdown. Existing build directories are refused; use a new `--output` directory when rebuilding. GitHub Actions deploys the site from `main` through GitHub Pages.
