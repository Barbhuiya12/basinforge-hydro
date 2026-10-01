# -*- coding: utf-8 -*-
"""
modèle pluie-débit annual GR1A

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

Mouelhi, S., Michel , C., Perrin, C. & Andreassian, V. (2006) Linking stream flow to
rainfall at the annual time step: the Manabe bucket model revisited. J. Hydrol. 328,
283-296, doi:10.1016/j.jhydrol.2005.12.022.
"""

# Vendored from LuMod 0.1.3.0: kernels only; cached Numba compilation.
import math
from math import tanh
import numpy as np
import numba as nb

@nb.njit(cache=True)
def _gr1a(prec, pet, x):
    """
    modèle pluie-débit annual GR1A
    """
    n = len(prec)
    qt = np.zeros(n, dtype=np.float32)
    for t in range(n):
        if t == 0:
            sub = prec[t] / (x * pet[t])
        else:
            sub = (0.7 * prec[t] + 0.3 * prec[t-1]) / (x * pet[t])
        qt[t] = prec[t] * (1.0 - 1.0 / (1.0 + sub ** 2.0) ** 0.5)
    return qt
