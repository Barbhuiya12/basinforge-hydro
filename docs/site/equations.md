# Equations and implementations

This package contains named model **variants**. The equations below describe the implemented variants and make the time step, units, initial states and routing choices explicit. They are not blanket claims of equivalence to every implementation carrying the same model name. Source links point to the vendored equations. `P`, `E`, `Q` and stores are water depth in millimetres per model step unless a routed volume or discharge is stated.

## GR4J daily kernel (LuMod 0.1.3.0)

States are production store `S` (capacity `x1` mm), routing store `R` (capacity `x3` mm), and the two unit-hydrograph queues. Initial stores are fractions `ps0*x1` and `rs0*x3`; queues start empty. Let `Pn=max(P-E,0)`, `En=max(E-P,0)`. For `P>E`,

$$
\mathrm{tanhPn}=\tanh(P_n/x_1),\quad P_s=\frac{x_1(1-(S/x_1)^2)\mathrm{tanhPn}}{1+(S/x_1)\mathrm{tanhPn}},\quad P_r=P_n-P_s.
$$

For `E>=P`,

$$
E_s=\frac{S(2-S/x_1)\tanh(E_n/x_1)}{1+(1-S/x_1)\tanh(E_n/x_1)},\quad P_s=P_r=0.
$$

Then `S*=S-Es+Ps`; percolation is `Perc=S* - S*/(1+(S*/(2.25 x1))^4)^(1/4)`, with `S=S*-Perc` and `P_r += Perc`. The `x4` unit hydrographs use ordinates that are successive differences of `F1(t)=min(max(t/x4,0),1)^2.5` and `F2(t)=0.5(t/x4)^2.5` up to `x4`, then `1-0.5(2-t/x4)^2.5` up to `2x4`, then one. `90%` of routed input enters UH1, `10%` UH2. Groundwater exchange is `F=x2(R/x3)^3.5`; routing store is updated by UH1 plus `F`, clipped at zero, then nonlinear routing release uses exponent four. Direct release is `max(0,0.1*UH2+F)`; total is direct plus routing-store release. [Pinned equation kernel](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/lumod/gr4j_model.py).

## GR2M monthly kernel (LuMod 0.1.3.0)

Initial production storage is `s0*x1` mm and routing storage `r0*60` mm. With `phi=tanh(P/x1)` and `psi=tanh(E/x1)`, production store transforms as `S1=(S+x1 phi)/(1+phi S/x1)`, `P1=P+S-S1`, `S2=S1(1-psi)/(1+psi(1-S1/x1))`, then capacity correction `S=S2/(1+(S2/x1)^3)^(1/3)`. The effective input is `P1+S2-S`. Add this to routing storage `R1`; apply exchange/scaling `R2=x2(R+P1+S2-S)`. Monthly runoff is `Q=R2^2/(R2+60)` and the next routing state is `R=R2-Q`. [Pinned kernel](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/lumod/gr2m_model.py).

## GR1A annual kernel (LuMod 0.1.3.0)

For the first year `u=P/(x E)`. Thereafter `u=(0.7 P_t+0.3 P_{t-1})/(x E_t)`. Annual runoff depth is `Q=P_t[1-(1+u^2)^(-1/2)]`. This implementation uses the immediately preceding annual precipitation and requires positive annual PET. [Pinned kernel](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/lumod/gr1a_model.py).

## HYMOD2 daily kernel (LuMod variant)

This is the source implementation of HYMOD2, not the classic five-parameter model. Set `Cmax=Wmax/(1+b)`, `b=log2(1/(1-beta/2))`, and `C(W)=Cmax(W/Wmax)^(1+b)`. Given previous soil water `W`, first calculate overflow `Peff2=max(0,P+W-Wmax)`, infiltration `I=P-Peff2`, and interim water `W*=min(Wmax,I+W)`. Then `Peff1=max(0,I+C(W)-C(W*))`, total effective rain `Peff=Peff1+Peff2`. The ET coefficient is `k=kmin+(kmax-kmin)(C(W*)/Cmax)^ce`, with `kmin=llet*kmax`, `ce=log2(1/(1-cexp/2))`; ET is `k*min(PET,C(W*))`. Soil content after ET is inverted through the capacity curve to update `W`. Effective rain partitions into quick `alpha*Peff` and slow `(1-alpha)*Peff`. Slow and each of `nres` serial quick stores are linear reservoirs (`out=k*store`; next store `max(0,store-out+inflow)`). Initial soil storage is `w0*Wmax`; quick and slow stores use `wq0` and `ws0`. [Pinned source equations](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/lumod/hymod_model.py).

## HBV-light snow daily variant

Temperature-index snow uses `M=min(Snow,dd(T-Tt))` for `T>=Tt` and `M=0` otherwise; below threshold all precipitation becomes snow, otherwise liquid input is `P+M`. Effective precipitation is `Pliq(SM/FC)^beta`, with remaining liquid infiltrating. The pinned source passes the initial parameter `s0` into its ET routine at each step: `ET=PET` if `s0>pwp`, otherwise `ET=PET*s0/(pwp*FC)`. This follows the implementation even though it does not use the evolving `SM` state for ET. The upper store receives runoff and successively releases threshold flow `k0*max(S1-lthres,0)`, interflow `k1*S1`, and percolation `kp*S1`, each limited by available upper-store water. The lower store receives percolation and releases `k2*S2`. Total runoff is routed with a triangular unit hydrograph governed by `maxbas`. Initial snow, soil fraction and upper/lower stores are `snow0`, `s0*FC`, `w01` and `w02`; routing queues start empty. [Pinned kernel](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/lumod/hbv_model.py).

## MILC daily variant

The single-layer soil water balance uses a capacity-dependent infiltration fraction `(1-(W/Wmax)^alpha)`, actual ET `max(0,PET*W/Wmax)`, and power-law drainage `KS*(W/Wmax)^m`, partitioned into baseflow `(1-nu)` and percolation `nu`. Excess rainfall is runoff. The package supplies explicit PET, so the upstream PET submodel is not called. The upstream GIUH routing uses its vendored tabulated curve and `dt=0.2`; the lookup table and gamma/Nash convolution are part of the pinned kernel. Initial soil fraction is `w0`; channel-routing queues initialize empty. [Pinned kernel and table](https://github.com/Barbhuiya12/basinforge-hydro/tree/main/src/basinforge/_vendor/lumod).

## GR3J, GR5J and GR6J

These are the named equations at the pinned `hydromodel` revision. The model family uses a production store with nonlinear rainfall/evaporation transformations, S-curve unit hydrograph routing, exchange terms and variant-specific additional stores/fluxes. For GR3J, production capacity is fixed at 330 mm; initial production and routing stores are set by the pinned source's sinusoidal initial-state formulas; the routing exchange is `F=x2(R/x2)^4`, and runoff is the sum of the two routed components. GR5J and GR6J add variant-specific states, exchange or evapotranspiration terms. Full terms and parameter ordering are kept in the cited executable source rather than replaced with textbook-family shorthand: [GR3J](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/hydromodel/gr3j.py), [GR5J](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/hydromodel/gr5j.py), [GR6J](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/hydromodel/gr6j.py). Initial states and helper equations in that implementation are part of the model contract.

## Classic HYMOD and XAJ

`HYMOD_CLASSIC` is the separate five-parameter hydromodel implementation: its complete soil curve, quick/slow partition, serial reservoirs, and initial-state defaults are given in [pinned source](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/hydromodel/hymod.py). `XAJ` and `XAJ_MZ` implement the source's three-layer tension-water accounting, runoff generation, free-water partitioning and channel routing; their full flux/state equations, parameter names/order and unit hydrograph are in [XAJ source](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/hydromodel/xaj.py). XAJ_MZ changes source equations and parameterization; it is not a cosmetic name variant.

## SMART daily wrapper

Each daily `P` and `PET` depth is apportioned uniformly to 24 hourly calls to the pinned SMARTpy catchment and river step equations. The catchment returns hourly runoff-component discharges; their sum enters a linear river store with `Qriver=Sriver/(RK*3600)`, and `Sriver` is advanced by hourly inflow volume less outflow volume, constrained nonnegative using the upstream 95% availability rule. Soil layers initialize equally at `Z/12` mm; runoff-routing stores initialize empty. Daily simulated depth is the sum of hourly river volumes divided by catchment area. This daily-to-hourly disaggregation is a forcing assumption. [Catchment and river equations](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/_vendor/smartpy/structure.py).

## ABCD monthly water balance

With previous soil store `S` and precipitation `P`, available water is `W=S+P`. The rationalized root is algebraically identical to the literal root: `Y=2bW/[W+b+sqrt((W+b)^2-4abW)]`. Soil after ET is `S'=Y exp(-PET/b)`, so `AET=Y-S'`. Surplus `R=W-Y` partitions to groundwater recharge `cR` and quick flow `(1-c)R`; groundwater updates to `G'=(G+cR)/(1+d)`, and streamflow is `Q=(1-c)R+dG'`. Default initial stores are zero and the model is monthly. [Implementation](https://github.com/Barbhuiya12/basinforge-hydro/blob/main/src/basinforge/water_balance.py); [equation reference](https://abcd.walkerenvres.com/theory.html).

## MARRMoT structures

The optional MARRMoT implementations follow the exact vendored `.m` `model_fun` state derivatives, source-ordered `p01...` values, flux helper equations, and implicit-Euler solver. `s01...` are explicit fixed stores (zero by default). These 47 distinct structures do not share one lumped-model equation. See the matching generated [model page](models/index.md) for source, frequency, calibrated parameter ranges and stores; use its exact upstream `model_fun` and called flux helper as the governing equations. They currently execute through Octave and are not yet native Python kernels.
