# Lumped model research inventory

This is a broad, source-linked inventory, **not an assertion that every lumped model ever developed has been found**, nor that every entry is implemented here. “Lumped” is a spatial configuration: some model families also have semi-distributed/distributed forms. Closely named variants can have different equations, solvers, states, and parameter meanings.

## Available now

Version 0.2.0 has 14 Python models: LuMod GR4J, GR2M, GR1A, modified HYMOD2, modified HBV-light and MILC; hydromodel GR3J, GR5J, GR6J, classic HYMOD, XAJ and XAJ_MZ; SMARTpy SMART; and native monthly ABCD. Additionally all 47 MARRMoT structures below have an optional persistent Octave adapter. `list_models()` lists Python models; `list_models(include_optional=True)` lists all 61 selectable implementations. Overlapping family names are intentionally not counted as distinct original families.

The six LuMod adapters use [LuMod](https://zaul_ae.gitlab.io/lumod-docs/). The other engine revisions, licenses and compatibility changes are documented in [THIRD_PARTY.md](../THIRD_PARTY.md). Numerical consistency tests do not establish field skill or source-equivalence with every variant of a named model.

## Other established families / integration candidates

| Family | Official implementation/reference | Current BasinForge status |
| --- | --- | --- |
| GR3J, GR5J, GR6J | [INRAE GR models](https://webgr.inrae.fr/eng/tools/hydrological-models), [hydromodel](https://github.com/OuyangWenyu/hydromodel) | Runnable hydromodel variants; airGR equivalence unverified |
| CemaNeige + GR models | [INRAE CemaNeige](https://webgr.inrae.fr/eng/tools/hydrological-models), [RavenPy](https://ravenpy.readthedocs.io/en/latest/notebooks/04_Emulating_hydrological_models.html) | Research only; not equivalent to standalone GR4J |
| Classic five-parameter HYMOD | [hydromodel](https://github.com/OuyangWenyu/hydromodel), [SPOTPY example](https://github.com/thouska/spotpy/blob/master/src/spotpy/examples/hymod_python/hymod.py) | Runnable HYMOD_CLASSIC via hydromodel; MARRMOT_29 separate standardized structure |
| HBV-96, HBV-EC, TUW/HBV variants | [hydromad HBV](https://hydromad.github.io/articles/hbv.html), [RavenPy](https://ravenpy.readthedocs.io/en/latest/notebooks/04_Emulating_hydrological_models.html) | Research only; LuMod HBV is a particular modified variant |
| SAC-SMA / Sacramento | [RavenPy Sacramento](https://ravenpy.readthedocs.io/en/latest/notebooks/04_Emulating_hydrological_models.html), [eWater](https://ewater.atlassian.net/wiki/spaces/SD54/pages/53740103/Water+quantity+processes+-+Catchments+SRG) | MARRMOT_33 standardized structure runnable; original engines research only |
| Xinanjiang / XAJ, XAJ-MZ, XAJ-SLW | [hydromodel](https://github.com/OuyangWenyu/hydromodel) | XAJ/XAJ_MZ runnable; SLW routing variant not integrated |
| Dahuofang / DHF | [hydromodel](https://ouyangwenyu.github.io/hydromodel/) | Research only |
| SIMHYD, IHACRES | [hydromad](https://hydromad.github.io/reference/), [eWater](https://ewater.atlassian.net/wiki/spaces/SD54/pages/53740103/Water+quantity+processes+-+Catchments+SRG) | MARRMOT_18/05 standardized structures runnable; original engines research only |
| HMETS, MOHYSE, Canadian Shield, HYPR | [RavenPy emulators](https://ravenpy.readthedocs.io/en/latest/notebooks/04_Emulating_hydrological_models.html) | Research only; an emulator is not automatically identical to every original model |
| FLEX/SUPERFLEX structures | [SuperflexPy](https://superflexpy.readthedocs.io/en/latest/) | User-supplied model interface; no bundled adapter |
| TOPMODEL, TANK, NAM, SMAR, MODHYDROLOG, MCRM, HYCYMODEL, GSM-SOCONT, PRMS, CLASSIC, LASCAM, TCM, VIC-inspired lumped structures | [MARRMoT](https://github.com/wknoben/MARRMoT) | Standardized MARRMoT structures runnable via Octave; original engines not integrated |
| SMART | [SMARTpy](https://github.com/ThibHlln/smartpy) | Runnable daily-to-hourly Python adapter; uniform forcing assumption |
| ABCD | [Monthly equations](https://abcd.walkerenvres.com/theory.html) | Runnable monthly native water balance |
| AWBM | [hydromad AWBM](https://hydromad.github.io/reference/awbm.html) | Research only; soil accounting must be paired with appropriate routing |
| WAPABA, IHACRES, SAC-SMA original variants | [CSIRO PyGME](https://github.com/csiro-hydroinformatics/pygme) | Research only; compiled C and hydrodiy dependencies require separate validation |
| TUW/HBV | [TUWmodel](https://cran.r-project.org/package=TUWmodel) | Research only; R/compiled engine distinct from existing HBV implementations |
| PDM | [UKCEH official implementation](https://www.ceh.ac.uk/data/software-models/pdm-probability-distributed-model) | Research only; official source redistribution/license must be confirmed |
| CFE and TOPMODEL BMI | [NOAA NextGen model inventory](https://github.com/NOAA-OWP/NextGen-Info), [CFE](https://github.com/NOAA-OWP/cfe) | Research only; compiled engines and additional soil/catchment configuration |
| HEC-HMS lumped configurations | [USACE features](https://www.hec.usace.army.mil/software/hec-hms/features.aspx) | External system, not a bundled open-source Python model; event/continuous options differ |

The hydromodel package already offers multi-model calibration; BasinForge is **not the first** such package. RavenPy, hydromad, SuperflexPy, and SPOTPY also provide substantial modelling/calibration tools. The intended contribution here is explicit units/frequencies, lightweight prepared-array adapters, equal-weight shared-basin fitting, chronological validation, and reusable completed basin jobs.

## Complete 47-structure MARRMoT inventory

Names, parameter counts, and store counts below are transcribed from the [official model-file directory](https://github.com/wknoben/MARRMoT/tree/master/MARRMoT/Models/Model%20files). MARRMoT explicitly notes that its standardized structures **resemble but are not identical to** the original models. Some names represent experimental/unnamed structures rather than separately established model families.

**All entries below are integrated in BasinForge 0.2.0** under keys `MARRMOT_01` through `MARRMOT_47`, using the pinned v2 source and external Octave + optim. All 47 have controlled-forcing upstream parity and calibration-interface tests. This does not validate every model on real basins or guarantee convergence for arbitrary parameters. Source-derived parameter ranges/default midpoints need basin-specific judgment. The runtime is not bundled in the wheel.

Daily P/PET are mm/step; mean temperature °C is required for IDs 06, 12, 30, 31, 32, 34, 35, 37, 41, 43, 44 and 45. Parameters `p01...` follow each source class's exact order; fixed initial stores `s01...` default to zero. Generic names avoid incorrectly assigning the same meanings/units to parameters across structures. See source-class comments before supplying bounds.

| ID | Structure name in source | Parameters | Stores |
| --- | --- | ---: | ---: |
| 01 | collie1 | 1 | 1 |
| 02 | wetland | 4 | 1 |
| 03 | collie2 | 4 | 1 |
| 04 | newzealand1 | 6 | 1 |
| 05 | ihacres | 7 | 1 |
| 06 | alpine1 | 4 | 2 |
| 07 | gr4j | 4 | 2 |
| 08 | us1 | 5 | 2 |
| 09 | susannah1 | 6 | 2 |
| 10 | susannah2 | 6 | 2 |
| 11 | collie3 | 6 | 2 |
| 12 | alpine2 | 6 | 2 |
| 13 | hillslope | 7 | 2 |
| 14 | topmodel | 7 | 2 |
| 15 | plateau | 8 | 2 |
| 16 | newzealand2 | 8 | 2 |
| 17 | penman | 4 | 3 |
| 18 | simhyd | 7 | 3 |
| 19 | australia | 8 | 3 |
| 20 | gsfb | 8 | 3 |
| 21 | flexb | 9 | 3 |
| 22 | vic | 10 | 3 |
| 23 | lascam | 24 | 3 |
| 24 | mopex1 | 5 | 4 |
| 25 | tcm | 6 | 4 |
| 26 | flexi | 10 | 4 |
| 27 | tank | 12 | 4 |
| 28 | xinanjiang | 12 | 4 |
| 29 | hymod | 5 | 5 |
| 30 | mopex2 | 7 | 5 |
| 31 | mopex3 | 8 | 5 |
| 32 | mopex4 | 10 | 5 |
| 33 | sacramento | 11 | 5 |
| 34 | flexis | 12 | 5 |
| 35 | mopex5 | 12 | 5 |
| 36 | modhydrolog | 15 | 5 |
| 37 | hbv | 15 | 5 |
| 38 | tank2 | 16 | 5 |
| 39 | mcrm | 16 | 5 |
| 40 | smar | 8 | 6 |
| 41 | nam | 10 | 6 |
| 42 | hycymodel | 12 | 6 |
| 43 | gsmsocont | 12 | 6 |
| 44 | echo | 16 | 6 |
| 45 | prms | 18 | 7 |
| 46 | classic | 12 | 8 |
| 47 | IHM19 | 16 | 4 |

## Integration acceptance criteria

For each additional model: verify upstream license and redistribution rights; identify exact variant/timestep/state convention; validate forcing and discharge units; reproduce authoritative reference outputs; check dry/wet/snow/extreme boundary cases and conservation assumptions; verify optimizer bounds and state initialization; benchmark real record lengths; only then advertise it as supported.

Event runoff methods (e.g. SCS-CN + unit hydrograph) and distributed frameworks (e.g. SWAT, mHM) should not be silently presented as interchangeable continuous daily lumped models.

Survey performed during this build using primary project documentation and official source inventories. It is not a systematic literature review with an exhaustive search protocol.
