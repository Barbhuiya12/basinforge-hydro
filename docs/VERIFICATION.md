# Development verification

These checks establish an initial working package, not independent scientific certification.

## Real-record calibration

Run: `python examples/real_lumod_basins.py --workers 2 --maxiter 100`.
Three records distributed with LuMod 0.1.3.0, observed discharge interpreted as m³/s, upstream GR4J PET calculation, first 70% of each record used for training, first 365 daily steps excluded as warmup, remaining 30% used for validation. GR4J, differential evolution, seed 42, population multiplier 6, package search bounds and initial-state defaults. Results are local to this configuration; no observation data were invented.

| LuMod example | Record length | Calibration NSE | Validation NSE | Validation KGE (2009) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 10,957 days | 0.2401 | 0.1532 | 0.4304 |
| 2 | 3,287 days | 0.7175 | 0.5908 | 0.7495 |
| 3 | 1,460 days | 0.7188 | 0.6680 | 0.7712 |

All jobs completed without errors. The optimizer reported convergence, which is **not** proof of a global optimum or acceptable hydrological performance. Example 1 has a poor fit under this configuration and should not be described as a successful predictive model. Further work includes basin-specific priors, initial-state sensitivity, alternative PET, multiple seeds, and independent reference validation.

## Simulation microbenchmark

`python benchmarks/compare_lumod.py`: GR4J, real LuMod example 2 (3,287 daily steps), identical forcing and parameters, parity checked, JIT warmed, 20 repetitions, macOS ARM64, Python 3.14.3.

- LuMod public API median: 0.571 ms.
- Prepared-array BasinForge adapter median: 0.220 ms.
- Ratio: 2.59× for this particular warmed workload.

The difference is primarily wrapper overhead; equations are the same upstream kernels. This does not demonstrate universally faster calibration or linear multi-process scaling. Process startup/JIT and hardware affect results.

## Automated checks

`python -m pytest -q` covers the Python engines, unit conversions and leap years, forcing continuity, missing-observation handling, deterministic seeds, training/validation isolation, common-vector fitting, serial/process agreement, completed-job resume fingerprints, incompatible model rejection, actual record calibration, CLI/no-overwrite behavior, multi-start selection, scenario quantiles and report fingerprint/HTML escaping. The six added hydromodel kernels are compared to independent pinned upstream checkout outputs. SMART is checked against hourly upstream execution; monthly ABCD against a literal quadratic reference and step-by-step storage conservation.

The original 0.1.0 run had 24 passing tests. The 0.2.0 suite additionally provides optional Octave integration tests. Enable them with `BASINFORGE_TEST_MARRMOT=1`; use `BASINFORGE_OCTAVE` and `BASINFORGE_OCTAVE_PACKAGE_LIST` for a nonstandard installation. Default runs skip optional integration, rather than pretending Octave has been tested.

Final development run: **145 tests passed in 44.22 seconds**, with the optional Octave integration enabled. This is one macOS ARM64/Python 3.14.3/Octave 10.3.0 environment; Linux CI workflows are supplied but have not been run remotely. Cross-platform and cross-solver-version results are not certified by this local run.

Publishing checks subsequently passed 146 tests locally, including the site builder; GitHub's Python 3.11/3.13/3.14 jobs passed. The first Linux Octave run found one cross-runtime regression difference in MARRMOT_33, up to 2.96e-5 mm on the controlled fixture, rather than an interface failure. Its stored-reference comparison now uses an explicitly documented 1e-4 mm absolute envelope; the other 46 structures retain 1e-8 mm absolute / 1e-7 relative tolerances. Public discharge validation is unchanged: materially negative flows are rejected. The stored reference is not an exact floating-point oracle across all BLAS/Octave versions.

`python -m build` generates a wheel/source archive including model MATLAB sources, the parameter manifest, worker wrapper and retained licenses. Not published to PyPI. No independent equivalence to airGR or the original HBV-light executable is claimed.

## Optional MARRMoT verification

On this development machine, Octave 10.3.0 with optim 1.6.3, statistics 1.7.7 and struct 1.0.18 was installed in a temporary portable environment. All 47 structures are tested against separately invoked official source at revision `eeb7e152d4bc194a6fa9407e3d79e2e29ba7e201`. Reference generation uses `benchmarks/generate_references.py` with independent source checkouts, not the BasinForge adapter. Controlled forcing is explicitly artificial, not observed data. A fixed solver restart seed is applied in both reference and adapter runs.

All 47 also enter single-parameter, two-candidate calibration on a short wet fixture, including chronological holdout. These are interface checks, not effective full-model calibrations. Additional tests check full-history continuity, diagnostics, spawned multi-basin agreement and request-history-independent fallback solves. Upstream MARRMOT_33 produces roughly −1.6e-6 mm on the dry/empty-store reference fixture: raw parity is checked and the public simulation API is explicitly tested to reject that invalid discharge. It is not silently clipped. Arbitrary forcing/parameter combinations can still fail upstream numerical solvers.

## New-engine real-record smoke comparison

Command: `python examples/compare_real_models.py --models GR4J GR5J HYMOD_CLASSIC XAJ MARRMOT_29 --samples 12 --output results/v0.2-real-comparison`.

Actual LuMod example-2 observations (3,287 daily steps), LuMod GR4J-derived PET, first 70% training, 365-step warmup, remaining 30% validation; Latin-hypercube search, 12 candidates, seed 42 and default model bounds. No observations were invented. Training loss selects the fit, not validation performance.

| Implementation | Training NSE | Validation NSE | Validation KGE 2009 | Calibration elapsed |
| --- | ---: | ---: | ---: | ---: |
| GR4J / LuMod | 0.5947 | 0.5024 | 0.7514 | 0.003 s |
| GR5J / hydromodel | −0.0045 | −0.2551 | 0.3441 | 0.324 s |
| Classic HYMOD / hydromodel | 0.4413 | 0.4305 | 0.6638 | 0.159 s |
| XAJ / hydromodel | 0.3860 | 0.4058 | 0.6754 | 1.434 s |
| HYMOD structure / MARRMOT_29 | 0.5831 | 0.4899 | 0.6591 | 59.008 s |

Every search exhausted its budget; none establishes optimizer convergence. GR5J performed poorly and must not be advertised as a good predictive fit. Elapsed times exclude baseline/preflight startup, but include candidate evaluation and final train/full simulations; they are **not equal-work engine speed rankings**, since parameter counts/equations/solvers differ. The optional Octave backend is demonstrably slower here. Each fit has a local hydrograph/flow-duration report, parameters and simulation CSV. These results are not full field validation of all 61 implementations.
