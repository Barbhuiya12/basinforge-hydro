# Configuration arguments

Calibration settings are passed through `CalibrationConfig`. The [API reference](api.md#calibrationconfig) contains the exact constructor signature.

| Argument | Default | Meaning |
| --- | --- | --- |
| `method` | `"de"` | Differential evolution; `"lhs"` performs Latin-hypercube candidate search. |
| `objective` | `"nse"` | NSE, KGE, RMSE, log NSE, or supported weighted objective mapping. |
| `warmup` | `365` | Initial **model steps** excluded from scoring, not always days. |
| `calibration_end` | `None` | Explicit training end date; do not combine with `calibration_fraction`. |
| `calibration_fraction` | `None` | Optional chronological training fraction strictly between zero and one. |
| `validation_start` | `None` | Optional later validation start, after training. |
| `seed` | `42` | Optimizer random seed. |
| `maxiter` | `100` | Differential-evolution iteration budget. |
| `popsize` | `10` | Differential-evolution population multiplier. |
| `samples` | `1000` | Latin-hypercube candidate count. |
| `polish` | `False` | Optional local polishing after differential evolution. |
| `bounds` | `None` | Override supported calibration bounds by parameter name. |
| `fixed` | `{}` | Explicit parameter values held fixed during fitting. |

## Study choices

The default settings are software defaults, not basin-specific recommendations. Use model steps for warmup: a monthly model needs a different choice than a daily one. Without an explicit split, do not interpret training metrics as held-out validation.

Parameter names, ranges, fixed initial stores and temperature requirements are listed on each [model page](models/index.md). The model must match the forcing time step.

## Optional engine settings

`configure_marrmot(octave=..., package_list=..., timeout=300)` configures the Octave backend. See [Installation](installation.md) and the generated API for supported arguments. This backend is optional and is not a Python-only execution engine.
