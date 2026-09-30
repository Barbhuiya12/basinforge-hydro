# Useful next additions

Implemented in 0.2: 14 Python models, 47 optional MARRMoT structures, shared/independent multi-basin calibration, completed-job reuse, chronological validation, deterministic multi-start selection, parameter-scenario ensembles, HTML hydrograph/flow-duration reports and Octave diagnostics.

## Highest-value scientific improvements

1. Original-engine adapters for AWBM, SAC-SMA, IHACRES and WAPABA. Their MARRMoT relatives are not substitutes for original-model parity. Evaluate [hydromad](https://hydromad.github.io/reference/) and [CSIRO PyGME](https://github.com/csiro-hydroinformatics/pygme), including compiled/runtime dependencies, routing components and license notices.
2. SCE-UA/DDS for deterministic calibration and DREAM/MCMC for posterior estimation, using a pinned [SPOTPY](https://github.com/thouska/spotpy) adapter. Add convergence diagnostics and likelihood/noise assumptions; do not relabel scenario spread as uncertainty.
3. Repeated temporal/rolling-origin validation and leave-one-basin-out regionalization, with parameter transfer based on basin attributes. These differ from today's single shared vector.
4. Sensitivity analysis (Morris/Sobol), flood/low-flow signatures, bias and timing objectives, seasonal evaluations and explicit Pareto-front optimization. Keep objective units/scales clear.
5. Store/routing state export/import, spin-up convergence checks and genuine unfinished-optimizer checkpoint recovery. Current resume reuses completed jobs only.
6. Optional CAMELS/NetCDF/xarray loaders, PET calculations with explicit meteorological requirements, and missing-forcing quality reports. Do not fabricate or automatically interpolate unknown observations.
7. Snow-enabled original HBV/TUW/CemaNeige and Raven HMETS/MOHYSE adapters; hourly GR variants. Introduce forcing/time-step contracts before adding names to the registry.

## More demanding candidates

NOAA CFE/TOPMODEL/SAC-SMA BMI engines need compilation and additional catchment/soil/forcing configuration. XAJ-SLW/Dahuofang require their particular routing/geometry contracts. HEC-HMS is an external modeling system, not a redistributable Python kernel by default. PDM official-source licensing needs confirmation. These are research candidates, not currently available adapters.

## Acceptance gate for every new adapter

Pinned official source + verified license, exact parameter units/order/coupling, forcing frequency/units, state initialization/routing, independent reference outputs, dry/wet/snow/extreme checks, invalid-candidate handling, optimizer and spawned-worker tests, real-basin holdout evaluations and measured performance. Controlled-fixture tests establish interfaces and numerical consistency, not predictive skill. Broader field validation remains necessary for the current models too.
