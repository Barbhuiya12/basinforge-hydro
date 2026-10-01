# -*- coding: utf-8 -*-
"""
HYdrological MODel (HYMOD)

Rain-Runoff Model for daily simulation


Author:
Saul Arciniega Esparza
Hydrogeology Group, Faculty of Engineering,
National Autonomous University of Mexico
zaul.ae@gmail.com | sarciniegae@comunidad.unam.mx

Based on:
Roy, T., H. V. Gupta, A. Serrat-Capdevila, J. B. Valdes (2017). HYMOD2 Model MATLAB Code,
HydroShare, https://doi.org/10.4211/hs.26c1d7a19e544718851181ac6e9f0fdc

Reference:
Tirthankar Roy (royt@email.arizona.edu)
Copyright: Hoshin V Gupta and Tirthankar Roy (University of Arizona)

Roy, T., Gupta, H. V., Serrat-Capdevila, A. and Valdes, J. B.: Using satellite-based
evapotranspiration estimates to improve the structure of a simple conceptual
rainfall-runoff model, Hydrol. Earth Syst. Sci., 21(2), 879–896,
doi:10.5194/hess-21-879-2017, 2017.

Quan, Z., Teng, J., Sun, W., Cheng, T., & Zhang, J. (2015).
Evaluation of the HYMOD model for rainfall-runoff simulation using the GLUE method.
IAHS-AISH Proceedings and Reports, 368(August 2014), 180–185.
https://doi.org/10.5194/piahs-368-180-2015
"""

#%% Import libraries
# Vendored from LuMod 0.1.3.0: kernels only; cached Numba compilation.
import math
from math import tanh
import numpy as np
import numba as nb

@nb.njit(cache=True)
def _maximum_storage_capacity(wmax, b):
    # Compute cmax
    return wmax / (1.0 + b)


@nb.njit(cache=True)
def _soil_moisture_content(w, wmax, cmax, b):
    return cmax * (1.0 - (1.0 - (w / wmax) ** (1.0 + b)))


@nb.njit(cache=True)
def _soil_moisture_module(prec, w, wmax, cmax, b):

    cbeg = _soil_moisture_content(w, wmax, cmax, b)  # Contents at begining
    peff2 = max(0.0, prec + w - wmax)  # Compute overland flow if enough precipitation
    infil = prec - peff2  # precipitation that does not go to overland flow
    w = min(wmax, infil + w)  # Intermediate height
    cinit = _soil_moisture_content(w, wmax, cmax, b)  # Intermediate contents
    peff1 = max(0.0, infil + cbeg - cinit)
    peff = peff1 + peff2  # compute overland flow
    return w, cinit, peff, infil


@nb.njit(cache=True)
def _compute_et(pet, cinit, cmax, kmin, kmax, ce):
    """
    Compute evpotranspiration related to the soil moisture state
    """
    k = kmin + (kmax - kmin) * (cinit / cmax) ** ce
    return k * min(pet, cinit)


@nb.njit(cache=True)
def _flow_partitioning(alpha, peff):
    xs = (1.0 - alpha) * peff  # slow flow
    xq = alpha * peff          # quick flow
    return xq, xs


@nb.njit(cache=True)
def _linear_reservoir(storage, inflow, k):
    """
    Compute linear reservoir simulation
    """
    outflow = k * storage
    sto = max(0.0, storage - outflow + inflow)
    return sto, outflow


@nb.njit(cache=True)
def _hymod(prec, pet, area, wmax, w0, wq0, ws0, alpha, beta, cexp, nres, ks, kq, kmax, llet):

    # Initial parameters
    n = len(prec)
    nres = int(nres)  # number of quick reservoirs
    w = w0 * wmax  # water storage in mm
    x_slow = ws0   # initial slow storage
    x_quick = wq0 + np.zeros(nres, dtype=np.float32)  # initial quick storage

    # Convert from scaled B (0-2) to unscaled b (0 - Inf)
    beta = min(max(beta, 0), 2)
    if beta == 2:
        b = 10.0 ** 6.0
    else:
        b = np.log(1.0 - beta / 2.0) / np.log(0.5)
    # Convert from scaled CE (0-2) to unscaled ce (0 - Inf)
    cexp = min(max(cexp, 0), 2)
    if cexp == 2:
        ce = 10.0 ** 6.0
    else:
        ce = np.log(1.0 - cexp / 2.0) / np.log(0.5)
    # Maximum capacity of soil zone
    cmax = _maximum_storage_capacity(wmax, b)
    kmin = llet * kmax

    # Create empty arrays
    qd = np.zeros(n, dtype=np.float32)  # routed quick flow
    qb = np.zeros(n, dtype=np.float32)  # routed slow flow
    peff = np.zeros(n, dtype=np.float32)  # effective precipitation
    infil = np.zeros(n, dtype=np.float32)  # infiltration
    et = np.zeros(n, dtype=np.float32)  # evapotranspiration
    ww = np.zeros(n, dtype=np.float32)  # water content
    wq = np.zeros(n, dtype=np.float32)  # mean storage in quick storages
    ws = np.zeros(n, dtype=np.float32)  # storage in slow storage

    for t in range(n):

        # Soil moisture computation
        w, cinit, peff[t], infil[t] = _soil_moisture_module(prec[t], w, wmax, cmax, b)
        # Compute evapotranspiration
        et[t] = _compute_et(pet[t], cinit, cmax, kmin, kmax, ce)
        # Update storage
        cend = min(max(cinit - et[t], 0.0), cmax)
        w = wmax * (1.0 - (1.0 - cend / cmax) ** (1.0 / (1.0 + b)))
        # peff partitioning
        uq, us = _flow_partitioning(alpha, peff[t])
        # Slow reservoir
        x_slow, qsout = _linear_reservoir(x_slow, us, ks)
        # Quick reservoir
        inflow = uq
        for i in range(nres):
            x_quick[i], qqout = _linear_reservoir(x_quick[i], inflow, kq)
            inflow = qqout
        # Save results
        qd[t] = qqout
        qb[t] = qsout
        ww[t] = w / wmax
        wq[t] = np.mean(x_quick)
        ws[t] = x_slow

    factor = area * 1000. / 86400.  # convert mm/d to m3/s
    qd *= factor
    qb *= factor
    qt = qd + qb
    # qt=1, qd=1, qb=2, peff=3, infil=4, et=5, ww=6, wq=7, ws=8
    return qt, qd, qb, peff, infil, et, ww, wq, ws
