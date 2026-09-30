"""Native ABCD equations (Thomas 1981), with explicit monthly accounting.

Equations independently implemented from the cited mathematical description;
not copied from a repository without a redistribution license.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def abcd_components(precipitation, pet, a, b, c, d, soil0=0.0, groundwater0=0.0):
    n = len(precipitation)
    q = np.empty(n)
    aet = np.empty(n)
    soil_series = np.empty(n)
    groundwater_series = np.empty(n)
    soil, groundwater = soil0, groundwater0
    for i in range(n):
        available = soil + precipitation[i]
        # Algebraically rationalized root avoids cancellation at a tiny a.
        discriminant = max(0.0, (available + b)**2 - 4*a*b*available)
        y = 2*b*available / (available + b + np.sqrt(discriminant))
        soil = y * np.exp(-pet[i] / b)
        aet[i] = y - soil
        surplus = max(0.0, available - y)
        groundwater = (groundwater + c*surplus) / (1+d)
        q[i] = (1-c)*surplus + d*groundwater
        soil_series[i] = soil
        groundwater_series[i] = groundwater
    return q, aet, soil_series, groundwater_series


def _abcd(basin, parameters):
    return abcd_components(basin.precipitation, basin.pet, *[parameters[name] for name in ["a", "b", "c", "d", "soil0", "groundwater0"]])[0]


def water_balance_registry():
    from .models import Model
    return {"ABCD": Model("ABCD", "monthly", {"a": 0.95, "b": 250.0, "c": 0.5, "d": 0.1, "soil0": 0.0, "groundwater0": 0.0}, {"a": (0.001, 1), "b": (1, 2000), "c": (0, 1), "d": (0.001, 1)}, _abcd, "Thomas (1981) ABCD monthly equations; native rationalized root; explicit zero initial stores")}
