# Third-party scientific implementations

BasinForge is an independent workflow package, not an official successor or affiliate of these projects. Cite both the model's scientific literature and the actual implementation when publishing results. Original source copyright notices remain in vendored files.

## LuMod

Dependency `lumod==0.1.3.0`, Saul Arciniega Esparza and contributors. Six direct-kernel adapters retain upstream equations. [Official source](https://gitlab.com/Zaul_AE/lumod) and [documentation](https://zaul_ae.gitlab.io/lumod-docs/). Not vendored. GPL-3.0; dependency distributions supply their own source/license.

## hydromodel

Wenyu Ouyang and contributors, [official repository](https://github.com/OuyangWenyu/hydromodel), revision `89d7a8ed1d72ce4fffbbd9897490b089382ecbac`. Eight selected model/helper files are vendored under `src/basinforge/_vendor/hydromodel` for GR3J, GR5J, GR6J, HYMOD, XAJ and XAJ_MZ. Imports are changed from `hydromodel.models` to the private BasinForge namespace; equations are unchanged. The package's data/geospatial stack is not copied or installed.

Upstream's metadata advertises MIT but the actual root LICENSE at this revision contains GPL v3. BasinForge retains that LICENSE and conservatively distributes the incorporated code under GPL v3, not MIT. XAJ safety bounds exclude a few zero singularities; upstream parameter coupling and integer routing behavior are retained. GR3J/GR6J initial transients are implementation-specific, not evidence of airGR equivalence.

## MARRMoT

Wouter Knoben, Luca Trotter, Clara Brandes and other contributors, [official repository](https://github.com/wknoben/MARRMoT), revision `eeb7e152d4bc194a6fa9407e3d79e2e29ba7e201`, v2 source. 174 model/base/flux/solver/helper `.m` files are vendored in `src/basinforge/_vendor/marrmot`, together with the full GPL v3 LICENSE. Original paths are flattened; filenames and scientific equations are retained. The 47 standardized structures are not identical to the original models that inspired them. [MARRMoT v2 paper](https://gmd.copernicus.org/articles/15/6359/2022/).

One compatibility modification in `MARRMoT_model.m`: the `rerunSolver` callback `@obj.ODE_approx_IE` becomes `@(S) obj.ODE_approx_IE(S)`. This avoids an Octave optim/lsqnonlin bound-method dispatch error without changing the ODE. BasinForge's separate worker sets `rng(0, 'twister')` for each run because upstream fallback solvers use random restart guesses. Thus results do not depend on request history. The adapter clips negative discharge only within 1e-8 mm of zero; diagnostics retain raw values. Numerical solvers are not guaranteed identical across Octave versions.

## SMARTpy

Dependency `smartpy==0.2.2`, Thibault Hallouin and contributors, [official hydrological project](https://github.com/ThibHlln/smartpy), GPL v3. Not the similarly named Tezos development tool. Uses explicit Python catchment/river step functions, not an optional unversioned C++ acceleration module. BasinForge allocates daily P/PET uniformly to 24 hourly substeps. Routing stores start empty, soil stores half-full. This forcing disaggregation is a stated modeling assumption, not observed subdaily weather.

## ABCD

Native implementation of Thomas's monthly four-parameter water-balance equations, independently checked against the literal quadratic expression and storage conservation. [Equation reference](https://abcd.walkerenvres.com/theory.html). No third-party implementation is copied. Initial soil and groundwater stores are explicit, default zero. Monthly frequency is enforced.

## Distribution

BasinForge's own code is GPL-3.0-only. Included upstream notices retain their original terms (including any later-version permissions). Retain all LICENSE files, attribution and modification notices when redistributing. Octave and its packages are external runtime dependencies, not bundled binaries.
