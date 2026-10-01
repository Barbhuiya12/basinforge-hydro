# -*- coding: utf-8 -*-
"""
Modello Idrologico Lumped in Continuo (MILC)

Rain-Runoff Model for daily simulation


Author:
Saul Arciniega Esparza
Hydrogeology Group, Faculty of Engineering,
National Autonomous University of Mexico
zaul.ae@gmail.com | sarciniegae@comunidad.unam.mx


Based on:
MISDc Rainfall-Runoff Model (https://github.com/IRPIhydrology/MISDc)

Reference:
Brocca, L., Liersch, S., Melone, F., Moramarco, T., Volk, M. (2013).
Application of a model-based rainfall-runoff database as efficient tool for flood risk management.
Hydrology and Earth System Sciences Discussion, 10, 2089-2115.
"""

# %% Import libraries
# Vendored from LuMod 0.1.3.0: kernels only; cached Numba compilation.
import math
from math import tanh
import numpy as np
import numba as nb
from pathlib import Path

IUH_DATA = np.loadtxt(Path(__file__).with_name("milc_iuh.txt"))
LOOKUP_TABLE = np.array([
    1, 1, 2, 6, 24, 120, 720, 5040, 40320,
    362880, 3628800, 39916800, 479001600,
    6227020800, 87178291200, 1307674368000,
    20922789888000, 355687428096000, 6402373705728000,
    121645100408832000, 2432902008176640000], dtype="int64")

@nb.njit(cache=True)
def factorial(n):
    # Factorial function to be used in numba functions
    if n > 20:
        raise ValueError
    return LOOKUP_TABLE[n]


@nb.njit(cache=True)
def _actual_evapotranspiration(pet, w, wmax):
    # Compute evpotranspiration
    return max(0.0, pet * w / wmax)


@nb.njit(cache=True)
def _runoff(prec, infil):
    # Compute runoff
    return max(0.0, prec - infil)


@nb.njit(cache=True)
def _infiltration(prec, w, wmax, alpha):
    # Compute infiltlration
    infil = max(0.0, prec * (1. - (w / wmax) ** alpha))
    # Check soil saturation
    if infil + w >= wmax:
        water_excess = infil + w - wmax
        infil -= water_excess
    return infil


@nb.njit(cache=True)
def _baseflow(w, wmax, m, ks, nu):
    # Compute baseflow
    baseflow = (1.0 - nu) * ks * (w / wmax) ** m
    return max(0.0, baseflow)


@nb.njit(cache=True)
def _percolation(w, wmax, m, ks, nu):
    # Compute percolation
    perc = nu * ks * (w / wmax) ** m
    return max(0.0, perc)


@nb.njit(cache=True)
def _water_content(w, wmax):
    # Compute Water Content
    return w / wmax


@nb.njit(cache=True)
def _iuh_comp(gamma, area, dt, delta_T):
    """
    Calculation of geomorphological Instantaneos Unit Hydrograph
    using the geomorphological approach of Gupta et al. (1980)

    Inputs:
        gamma      >   [float] coefficient lag-time relationship
                           Lag = gamma * 1.19 * area ^ 0.33
        area       >   [float] basin area in squared kilometers
        dt         >   [float] computational time step for flood
                           event simulation, in hours
        delta_T    >   [float] input time step of the time series

    Outputs:
        IUH        >   [array] output Instaneous Unit Hydrograph
    """
    lag = (gamma * 1.19 * area ** 0.33) / delta_T
    hp = 0.8 / lag
    t = IUH_DATA[:, 0] * lag
    IUH0 = IUH_DATA[:, 1] * hp
    t_i = np.arange(0, np.max(t), dt)
    IUH = np.interp(t_i, t, IUH0)
    return IUH


@nb.njit(cache=True)
def _iuh_nash(n, gamma, area, dt, delta_T):
    """
    Nash Instantaneos Unit Hydrograph used for baseflow routine

    Inputs:
        n          >   [float] model parameter
        gamma      >   [float] coefficient lag-time relationship
                           Lag = gamma * 1.19 * area ^ 0.33
        area       >   [float] basin area in squared kilometers
        dt         >   [float] computational time step for flood
                           event simulation, in hours
        delta_T    >   [float] input time step of the time series
    """
    K = (gamma * 1.19 * area ** 0.33) / delta_T
    t = np.arange(0, 100, dt)
    IUH = (t / K) ** (n - 1) * np.exp(-t / K) / factorial(int(n - 1)) / K
    return IUH


@nb.njit(cache=True)
def _convolution_giuh(runoff, baseflow, area, gamma, dt):
    """
    Compute streamflow hydrograph at the catchment outlet
    using Geomorphological Instantaneos Unit Hydrograph for runoff and
    Nash Instantaneos Unit Hydrograph for baseflow.

    Inputs:
        runoff     >   [array] runoff serie
        baseflow   >   [array] baseflow serie
        dt         >   [float] computational time step for flood
                           event simulation, in hours
        delta_T    >   [float] input time step of the time series
    """
    delta_T = 24.0    # time delta in hours
    n = len(runoff)

    # Compute runoff IUH
    IUH1 = _iuh_comp(gamma, area, dt, delta_T) * dt
    IUH1 /= np.sum(IUH1)

    # Compute baseflow IUH
    IUH2 = _iuh_nash(1.0, 0.5 * gamma, area, dt, delta_T) * dt
    IUH2 /= np.sum(IUH2)

    # Convolution to compute hydrographs
    qs_int = np.interp(np.arange(0, n, dt), np.arange(n), runoff)
    bf_int = np.interp(np.arange(0, n, dt), np.arange(n), baseflow)

    temp1 = np.convolve(IUH1, qs_int)
    temp2 = np.convolve(IUH2, bf_int)

    # Compute total flow and baseflow
    dt1 = np.round(1. / dt)
    idx = np.arange(0, n * dt1, dt1, dtype=np.int32)

    factor = area * 1000. / delta_T / 3600.
    qd = temp1[idx] * factor  # routed runoff
    qb = temp2[idx] * factor  # routed baseflow

    return qd, qb


@nb.njit(cache=True)
def _milc(prec, pet, area, gamma, w0, wmax, alpha, m, ks, nu, dt):
    """
    Modello Idrologico Lumped in Continuo (MILC)
    """

    # Initial parameters
    n = len(prec)
    w = w0 * wmax  # water storage in mm
    # ks * 24      # convert mm/hr to mm

    # Create empty arrays
    runoff = np.zeros(n, dtype=np.float32)    # direct flow
    baseflow = np.zeros(n, dtype=np.float32)  # baseflow
    et = np.zeros(n, dtype=np.float32)        # evapotranspiration
    infil = np.zeros(n, dtype=np.float32)     # infiltration
    perc = np.zeros(n, dtype=np.float32)      # percolation
    ww = np.zeros(n, dtype=np.float32)        # water content

    for t in range(n):
        # Surface processes
        infil[t] = _infiltration(prec[t], w, wmax, alpha)
        runoff[t] = _runoff(prec[t], infil[t])
        w += infil[t]  # update Water Storage
        # Subsurface processes
        et[t] = _actual_evapotranspiration(pet[t], w, wmax)
        w -= et[t]  # update Water Storage
        # Deep processes
        baseflow[t] = _baseflow(w, wmax, m, ks, nu)
        perc[t] = _percolation(w, wmax, m, ks, nu)
        w -= baseflow[t] + perc[t]  # update Water Storage
        # Compute Water Content
        ww[t] = _water_content(w, wmax)

    # Flow routing using IUH
    qd, qb = _convolution_giuh(runoff, baseflow, area, gamma, dt)
    qt = qb + qd

    return qt, qd, qb, runoff, baseflow, et, infil, perc, ww
