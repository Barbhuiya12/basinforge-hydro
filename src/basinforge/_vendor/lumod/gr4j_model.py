# -*- coding: utf-8 -*-
"""
modele du Genie Rural a 4 parametres Journalier (GR4j)

Rain-Runoff Model


Author:
Saul Arciniega Esparza
Hydrogeology Group, Faculty of Engineering,
National Autonomous University of Mexico
zaul.ae@gmail.com | sarciniegae@comunidad.unam.mx

Based on:
Andrew MacDonald (andrew@maccas.net)
https://github.com/amacd31/pygr4j

Reference:
Perrin, C. (2002). Vers une amélioration d'un modèle global pluie-débit au travers d'une approche comparative.
La Houille Blanche, n°6/7, 84-91.
Perrin, C., Michel, C., Andréassian, V. (2003). Improvement of a parsimonious model for streamflow simulation.
Journal of Hydrology 279(1-4), 275-289.
"""

# Vendored from LuMod 0.1.3.0: kernels only; cached Numba compilation.
import math
from math import tanh
import numpy as np
import numba as nb

@nb.njit(cache=True)
def _reservoirs_evaporation(prec, pet, ps, x1):
    """
    Estimate net evapotranspiration and reservoir production
    """
    if prec > pet:
        evap = 0.
        snp = (prec - pet) / x1  # scaled net precipitation
        snp = min(snp, 13.)
        tsnp = tanh(snp)  # tanh_scaled_net_precip
        # reservoir production
        res_prod = ((x1 * (1. - (ps / x1) ** 2.) * tsnp)
                    / (1. + ps / x1 * tsnp))
        # routing pattern
        rout_pat = prec - pet - res_prod
    else:
        sne = (pet - prec) / x1  # scaled net evapotranspiration
        sne = min(sne, 13.)
        tsne = tanh(sne)  # tanh_scaled_net_evap
        ps_div_x1 = (2. - ps / x1) * tsne
        evap = ps * ps_div_x1 / (1. + (1. - ps / x1) * tsne)

        res_prod = 0  # reservoir_production
        rout_pat = 0  # routing_pattern

    return evap, res_prod, rout_pat


@nb.njit(cache=True)
def _s_curves1(t, x4):
    """
    Unit hydrograph ordinates for UH1 derived from S-curves.
    """
    if t <= 0:
        return 0
    elif t < x4:
        return (t / x4) ** 2.5
    else:  # t >= x4
        return 1


@nb.njit(cache=True)
def _s_curves2(t, x4):
    """
    Unit hydrograph ordinates for UH2 derived from S-curves.
    """
    if t <= 0:
        return 0
    elif t < x4:
        return 0.5 * (t / x4) ** 2.5
    elif t < 2 * x4:
        return 1 - 0.5 * (2 - t / x4) ** 2.5
    else:  # t >= x4
        return 1


@nb.njit(cache=True)
def _compute_unitary_hydrograph(x4):

    nuh1 = int(math.ceil(x4))
    nuh2 = int(math.ceil(2.0 * x4))
    uh1 = np.zeros(nuh1)
    uh2 = np.zeros(nuh2)
    uh1_ordinates = np.zeros(nuh1)
    uh2_ordinates = np.zeros(nuh2)

    for t in range(1, nuh1 + 1):
        uh1_ordinates[t - 1] = _s_curves1(t, x4) - _s_curves1(t - 1, x4)

    for t in range(1, nuh2 + 1):
        uh2_ordinates[t - 1] = _s_curves2(t, x4) - _s_curves2(t - 1, x4)

    ouh1 = uh1_ordinates
    ouh2 = uh2_ordinates
    return ouh1, ouh2, uh1, uh2


@nb.njit(cache=True)
def _compute_hydrograph(rout_pat, ouh1, ouh2, uh1, uh2):
    """
    Daily hydrpgraph for catchment routine
    """
    for i in range(0, len(uh1) - 1):
        uh1[i] = uh1[i + 1] + ouh1[i] * rout_pat
    uh1[-1] = ouh1[-1] * rout_pat

    for j in range(0, len(uh2) - 1):
        uh2[j] = uh2[j + 1] + ouh2[j] * rout_pat
    uh2[-1] = ouh2[-1] * rout_pat

    return uh1, uh2


@nb.njit(cache=True)
def _compute_exchange(uh1, rout_sto, x2, x3):
    # groundwater exchange
    gw_exc = x2 * (rout_sto / x3) ** 3.5
    rout_sto = max(0, rout_sto + uh1[0] * 0.9 + gw_exc)
    return gw_exc, rout_sto


@nb.njit(cache=True)
def _compute_discharge(uh2, gw_exc, rout_sto, x3):
    new_rout_sto = rout_sto / (1. + (rout_sto / x3) ** 4.0) ** 0.25
    qr = rout_sto - new_rout_sto
    rout_sto = new_rout_sto
    qd = max(0, uh2[0] * 0.1 + gw_exc)
    return qr, qd, rout_sto


@nb.njit(cache=True)
def _gr4j(prec, pet, x1, x2, x3, x4, ps0, rs0):

    # Create empty arrays
    n = len(prec)
    qtarray = np.zeros(n, dtype=np.float32)
    qdarray = np.zeros(n, dtype=np.float32)
    qrarray = np.zeros(n, dtype=np.float32)
    gwarray = np.zeros(n, dtype=np.float32)
    psarray = np.zeros(n, dtype=np.float32)
    rsarray = np.zeros(n, dtype=np.float32)

    # Initial parameters
    ouh1, ouh2, uh1, uh2 = _compute_unitary_hydrograph(x4)
    psto = ps0 * x1
    rsto = rs0 * x3

    # Compute water partioning
    for t in range(n):
        res = _reservoirs_evaporation(prec[t], pet[t], psto, x1)
        evap, res_prod, rout_pat = res

        psto = psto - evap + res_prod
        perc = psto / (1. + (psto / 2.25 / x1) ** 4.) ** 0.25
        rout_pat = rout_pat + (psto - perc)
        psto = perc

        uh1, uh2 = _compute_hydrograph(rout_pat, ouh1, ouh2, uh1, uh2)

        gw_exc, rsto = _compute_exchange(uh1, rsto, x2, x3)

        qr, qd, rsto = _compute_discharge(uh2, gw_exc, rsto, x3)
        qt = qr + qd

        # Save outputs
        qtarray[t] = qt  # total flow
        qdarray[t] = qd  # runoff
        qrarray[t] = qr  # baseflow
        gwarray[t] = gw_exc  # groundwater exchange
        psarray[t] = psto / x1  # production storage
        rsarray[t] = rsto / x3  # routing storage

    return qtarray, qdarray, qrarray, gwarray, psarray, rsarray
