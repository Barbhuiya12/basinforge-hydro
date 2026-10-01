# -*- coding: utf-8 -*-
"""
modèle pluie-débit mensuel GR2M

Rain-Runoff Model


Author:
Saul Arciniega Esparza
Hydrogeology Group, Faculty of Engineering,
National Autonomous University of Mexico
zaul.ae@gmail.com | sarciniegae@comunidad.unam.mx

Reference:
Mouelhi, S., 2003. Vers une chaîne cohérente de modèles pluie-débit conceptuels
globaux aux pas de temps pluriannuel, annuel, mensuel et journalier. Thèse de Doctorat,
ENGREF, Cemagref Antony, France, 323 pp.

Mouelhi, S., C. Michel, C. Perrin, and V. Andréassian (2006), Stepwise development of a two-parameter
monthly water balance model, J. Hydrol., 318, 200-214, https://doi.org/10.1016/j.jhydrol.2005.06.014
"""

# Vendored from LuMod 0.1.3.0: kernels only; cached Numba compilation.
import math
from math import tanh
import numpy as np
import numba as nb

@nb.njit(cache=True)
def _gr2m(prec, pet, s0, r0, x1, x2):
    """
    modèle pluie-débit mensuel GR2M
    """
    # Initial parameters
    s0 = s0 * x1
    r0 = r0 * 60

    # Output series
    n = len(prec)
    s = np.zeros(n, dtype=np.float32)
    r = np.zeros(n, dtype=np.float32)
    qt = np.zeros(n, dtype=np.float32)

    # Main loop
    for i in range(n):
        phi = np.tanh(prec[i] / x1)
        psi = np.tanh(pet[i] / x1)
        s1 = (s0 + x1 * phi) / (1.0 + phi * s0 / x1)
        p1 = prec[i] + s0 - s1
        s2 = (s1 * (1.0 - psi)) / (1.0 + psi * (1.0 - s1 / x1))
        s0 = s2 / (1.0 + (s2 / x1) ** 3.0) ** (1.0 / 3.0)
        s[i] = s0 / x1  # save state
        p2 = s2 - s0
        p3 = p1 + p2
        r1 = r0 + p3
        r2 = x2 * r1
        qt[i] = r2 ** 2.0 / (r2 + 60.0)
        r0 = r2 - qt[i]
        r[i] = r0 / 60.0  # save state

    return qt, s, r
