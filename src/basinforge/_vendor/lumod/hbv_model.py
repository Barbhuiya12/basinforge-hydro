# -*- coding: utf-8 -*-
"""
Conceptual Hydrologiska Byråns Vattenbalansavdelning (HBV) model

Rain-Runoff Model


Author:
Saul Arciniega Esparza
Hydrogeology Group, Faculty of Engineering,
National Autonomous University of Mexico
zaul.ae@gmail.com | sarciniegae@comunidad.unam.mx

Based on:
HRL (2021). HBV-EDU Hydrologic Model (https://www.mathworks.com/matlabcentral/fileexchange/41395-hbv-edu-hydrologic-model),
MATLAB Central File Exchange. Retrieved November 4, 2021.

Reference:
AghaKouchak A., Habib E., 2010, Application of a Conceptual Hydrologic
Model in Teaching Hydrologic Processes, International Journal of Engineering Education, 26(4), 963-973.
"""

# Vendored from LuMod 0.1.3.0: kernels only; cached Numba compilation.
import math
from math import tanh
import numpy as np
import numba as nb

@nb.njit(cache=True)
def _snow_accumulation(sn, prec, tmed, tthres, dd):
    # snow accumulation and snowmelt
    if tmed < tthres:
        sn += prec
        lw = 0.0
    else:
        sn = max(0, sn - dd * (tmed - tthres))
        lw = prec + min(sn, dd * (tmed - tthres))
    return sn, lw  # snow, liquid water


@nb.njit(cache=True)
def _effective_precipitation(w, inflow, fc, beta):
    # Compute effective precipitation
    return inflow * (w / fc) ** beta


@nb.njit(cache=True)
def _infiltration(prec, peff):
    # Compute infiltration
    return max(0.0, prec - peff)


@nb.njit(cache=True)
def _actual_evapotranspiration(pet, w, pwp, fc):
    # Compute actual evapotranspiration
    if w > pwp:
        et = pet
    else:
        et = pet * (w / (pwp * fc))
    return et


@nb.njit(cache=True)
def _near_surface_flow(w, k, lthres):
    # near surface flow computation
    return max(0.0, (w - lthres) * k)


@nb.njit(cache=True)
def _linear_reservoir(w, k):
    # linear reservoir discharge
    return w * k


@nb.njit(cache=True)
def _uh_traingular(maxbas):
    # triangular unitary hydrograph
    delay = maxbas
    tt = np.arange(1, np.ceil(delay) + 1)
    ff = 0.5 / (0.5 * (0.5 * delay) ** 2.0)
    d50 = 0.5 * delay
    tri = lambda t: max(ff * (t - d50) * np.sign(d50 - t) + ff * d50, 0)
    qu = np.zeros(len(tt))
    for i in range(len(tt)):
        h1 = tri(i)
        h2 = tri(i + 1)
        area = (h1 + h2) / 2.0
        qu[i] = area
    qu = qu / np.sum(qu)
    return qu


@nb.njit(cache=True)
def _convolution_giuh(inflow, area, maxbas):
    # Unitary hydrograph convulution
    n = len(inflow)
    qu = _uh_traingular(maxbas)
    qt = np.convolve(qu, inflow)
    qt = qt[np.arange(n)]
    factor = area / 86.4
    qt *= factor
    return qt


@nb.njit(cache=True)
def _hbv_light(prec, tmean, pet, area, maxbas, tthres, dd, fc, beta, pwp, k0, k1, k2, kp, lthres,
               snow0, s0, w01, w02):
    # Initial parameters
    n = len(prec)
    sm = s0 * fc  # initial soil moisture storage in mm
    s1 = w01  # upper reservoir storage in mm
    s2 = w02  # lower reservoir storage in mm
    sn = snow0  # initial snow equivalent thickness in mm

    # Create empty arrays
    snow = np.zeros(n, dtype=np.float32)  # snow accumulation
    lqw = np.zeros(n, dtype=np.float32)  # liquid water
    runoff = np.zeros(n, dtype=np.float32)  # direct flow
    et = np.zeros(n, dtype=np.float32)  # evapotranspiration
    infil = np.zeros(n, dtype=np.float32)  # infiltration
    totalflow = np.zeros(n, dtype=np.float32)  # total flow
    nsurflow = np.zeros(n, dtype=np.float32)  # near surface flow
    interflow = np.zeros(n, dtype=np.float32)  # interflow
    baseflow = np.zeros(n, dtype=np.float32)  # baseflow
    perc = np.zeros(n, dtype=np.float32)  # percolation
    ws = np.zeros(n, dtype=np.float32)  # soil moisture as a fraction of fc
    ws1 = np.zeros(n, dtype=np.float32)  # upper reservoir storage
    ws2 = np.zeros(n, dtype=np.float32)  # upper reservoir storage

    for t in range(n):
        # Snow accumulation
        sn, lqw[t] = _snow_accumulation(sn, prec[t], tmean[t], tthres, dd)
        # Surface processes
        runoff[t] = _effective_precipitation(sm, lqw[t], fc, beta)
        # Infiltration
        infil[t] = _infiltration(lqw[t], runoff[t])
        sm += infil[t]
        # Actual evapotranspiration
        et[t] = _actual_evapotranspiration(pet[t], s0, pwp, fc)
        sm -= et[t]
        # Upper soil layer discharge routine
        s1 += runoff[t]
        nsurflow[t] = _near_surface_flow(s1, k0, lthres)
        s1 -= nsurflow[t]
        interflow[t] = _linear_reservoir(s1, k1)
        s1 -= interflow[t]
        perc[t] = _linear_reservoir(s1, kp)
        s1 -= perc[t]
        # Lower soil layer discharge
        s2 += perc[t]
        baseflow[t] = _linear_reservoir(s2, k2)
        s2 -= baseflow[t]
        # Total Flow
        totalflow[t] = nsurflow[t] + interflow[t] + baseflow[t]
        # Save reservoirs
        snow[t] = sn
        ws[t] = sm / fc
        ws1[t] = s1
        ws2[t] = s2

    totalflow[:] = _convolution_giuh(totalflow, area, maxbas)
    # totalflow=0, runoff=1, nsurflow=2, interflow=3, baseflow=4
    # et=5, lqw=6, infil=7, perc=8, snow=9, ws=10, ws1=11, ws2=12
    return totalflow, runoff, nsurflow, interflow, baseflow, et, lqw, infil, perc, snow, ws, ws1, ws2
