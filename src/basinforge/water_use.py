"""Native, daily managed-water accounting in m3 per day.

Conceptual aquifer and reservoir accounting, not a spatial groundwater solver.
No CWatM/Pywr code is imported or copied. See the water-use guide for equations.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib

import numpy as np
import pandas as pd
from numba import njit
from scipy.optimize import linprog

from .models import Model, get_model


def _series(value, n, name, *, infinity=False):
    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        array = np.full(n, float(array))
    if array.shape != (n,) or np.any(np.isnan(array)) or np.any(array < 0) or (not infinity and not np.all(np.isfinite(array))):
        raise ValueError(f"{name} must be nonnegative and have one value per day (or a scalar).")
    array = np.array(array, dtype=float, order="C", copy=True)
    array.flags.writeable = False
    return array


@dataclass(frozen=True)
class WaterDemand:
    """Sector demand in m3/day. Lower priority numbers are served first.

    ``source`` is surface, groundwater, or mixed. Mixed users prefer surface
    water and can use groundwater for their remaining demand. Returns are
    generated from actual supplied water, never from unmet requests.
    """
    name: str
    demand: object
    source: str = "mixed"
    priority: int = 1
    consumption_fraction: float = 0.5
    groundwater_return_fraction: float = 0.0
    return_delay_days: int = 1
    max_withdrawal: object = np.inf

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Demand name must be nonempty.")
        if self.source not in {"surface", "groundwater", "mixed"}:
            raise ValueError("source must be surface, groundwater, or mixed.")
        for name in ("priority", "return_delay_days"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer.")
        for name in ("consumption_fraction", "groundwater_return_fraction"):
            if not np.isfinite(getattr(self, name)) or not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1].")


@dataclass(frozen=True)
class WaterUseConfig:
    """Daily conceptual stores; all volumes/capacities are m3.

    ``baseflow_fraction`` partitions natural-model runoff into aquifer recharge
    instead of adding a second copy of that water. External recharge must be
    supplied separately and must not duplicate natural-model runoff.
    """
    allocation: str = "priority"
    environmental_flow: object = 0.0
    pumping_capacity: object = np.inf
    external_recharge: object = 0.0
    baseflow_fraction: float = 0.0
    groundwater_recession: float = 0.0
    groundwater_initial: float = 0.0
    groundwater_capacity: float = np.inf
    reservoir_capacity: float = 0.0
    reservoir_initial: float = 0.0
    reservoir_release: object = np.inf
    reservoir_evaporation: object = 0.0

    def __post_init__(self):
        if self.allocation not in {"priority", "lp"}:
            raise ValueError("allocation must be priority or lp.")
        for name in ("baseflow_fraction", "groundwater_recession"):
            if not np.isfinite(getattr(self, name)) or not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1].")
        for name in ("groundwater_initial", "reservoir_initial", "reservoir_capacity"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative.")
        if np.isnan(self.groundwater_capacity) or self.groundwater_capacity < self.groundwater_initial:
            raise ValueError("groundwater_capacity must be at least groundwater_initial.")
        if self.reservoir_initial > self.reservoir_capacity:
            raise ValueError("reservoir_initial exceeds reservoir_capacity.")


@dataclass
class WaterUseResult:
    """Daily accounting table and per-sector supplied/consumed/unmet volumes."""
    daily: pd.DataFrame
    sectors: dict[str, pd.DataFrame]
    initial_storage: float

    @property
    def balance_error(self):
        return float(self.daily.balance_error.abs().max())

    def summary(self):
        return {"units": "m3", "maximum_daily_balance_error": self.balance_error,
                "river_outflow": float(self.daily.river_outflow.sum()),
                "consumed": float(self.daily.consumed.sum()),
                "unmet_demand": float(self.daily.unmet.sum()),
                "final_storage_including_pending_returns": float(self.daily.total_storage.iloc[-1])}


@njit(cache=True)
def _priority(demand, source, priorities, surface, groundwater):
    # Inputs are already sorted by priority; equal-priority ties use input order.
    supplied = np.zeros((len(demand), 2))
    for j in range(len(demand)):
        if source[j] != 1:
            supplied[j, 0] = min(demand[j], surface)
            surface -= supplied[j, 0]
        if source[j] != 0:
            supplied[j, 1] = min(demand[j] - supplied[j, 0], groundwater)
            groundwater -= supplied[j, 1]
    return supplied


def _linear(demand, source, priorities, surface, groundwater):
    """Lexicographic priority groups; maximum total supply within each group."""
    supplied = np.zeros((len(demand), 2))
    for priority in np.unique(priorities):
        indices = np.flatnonzero(priorities == priority)
        count = len(indices)
        constraints = np.zeros((count + 2, 2 * count))
        limits = np.r_[demand[indices], surface, groundwater]
        bounds = []
        for k, j in enumerate(indices):
            constraints[k, 2*k:2*k+2] = 1
            constraints[-2, 2*k] = 1
            constraints[-1, 2*k+1] = 1
            bounds.extend([(0, 0 if source[j] == 1 else None), (0, 0 if source[j] == 0 else None)])
        # Normalise to avoid solver feasibility tolerances in large-volume units.
        scale = max(1.0, float(np.max(demand[indices])))
        result = linprog(-np.ones(2*count), A_ub=constraints, b_ub=limits / scale,
                         bounds=bounds, method="highs")
        if not result.success:
            raise RuntimeError(f"Water allocation failed: {result.message}")
        # Preserve maximum supply, then prefer surface water to avoid pumping
        # unnecessarily. Equal-priority users are not guaranteed equal coverage.
        total = max(0.0, -result.fun)
        preferred = linprog(np.tile([0.0, 1.0], count), A_ub=constraints,
                            b_ub=limits / scale, A_eq=np.ones((1, 2*count)),
                            b_eq=[total], bounds=bounds, method="highs")
        if not preferred.success:
            raise RuntimeError(f"Water allocation source preference failed: {preferred.message}")
        values = np.maximum(0, preferred.x.reshape(count, 2) * scale)
        supplied[indices] = values
        surface = max(0.0, surface - values[:, 0].sum())
        groundwater = max(0.0, groundwater - values[:, 1].sum())
    return supplied


@njit(cache=True)
def _core(natural, upstream, demand, caps, source, priorities, consumption, gw_return,
          delay, env, pumping, recharge, fraction, recession, gw_initial, gw_capacity,
          res_capacity, res_initial, releases, evaporation, allocator):
    n, count = demand.shape
    horizon = n + (int(np.max(delay)) if count else 0) + 1
    surface_queue = np.zeros(horizon)
    groundwater_queue = np.zeros(horizon)
    daily = np.zeros((n, 20))
    sector = np.zeros((n, count, 6))
    gw, reservoir, pending = gw_initial, res_initial, 0.0
    previous = gw + reservoir
    for t in range(n):
        returned_surface = surface_queue[t]
        returned_groundwater = groundwater_queue[t]
        pending -= returned_surface + returned_groundwater
        gw += natural[t] * fraction + recharge[t] + returned_groundwater
        overflow = max(0.0, gw - gw_capacity)
        gw -= overflow
        surface = natural[t] * (1-fraction) + upstream[t] + returned_surface + overflow
        # Pumping precedes recession/baseflow, so pumping can reduce baseflow.
        evap, spill, release = 0.0, 0.0, 0.0
        if res_capacity > 0:
            reservoir += surface
            evap = min(reservoir, evaporation[t])
            reservoir -= evap
            spill = max(0.0, reservoir - res_capacity)
            reservoir -= spill
            release = min(reservoir, releases[t])
            reservoir -= release
            surface = spill + release
        # Retain enough groundwater to support today's environmental minimum
        # through recession when possible. This is not a long-term pumping rule.
        groundwater_reserve = max(0.0, env[t]-surface) / recession if recession > 0 else 0.0
        available_groundwater = min(max(0.0, gw-groundwater_reserve), pumping[t])
        allocation = allocator(np.minimum(demand[t], caps[t]), source, priorities,
                               max(0.0, surface - env[t]), available_groundwater)
        sw = allocation[:, 0].sum()
        pumped = allocation[:, 1].sum()
        surface = max(0.0, surface - sw)
        gw = max(0.0, gw - pumped)
        baseflow = gw * recession
        gw -= baseflow
        surface += baseflow
        consumed = 0.0
        immediate_surface, immediate_groundwater = 0.0, 0.0
        for j in range(count):
            supplied = allocation[j, 0] + allocation[j, 1]
            used = supplied * consumption[j]
            returned = supplied - used
            groundwater_return = returned * gw_return[j]
            surface_return = returned - groundwater_return
            consumed += used
            if delay[j] == 0:
                immediate_surface += surface_return
                immediate_groundwater += groundwater_return
            else:
                surface_queue[t+delay[j]] += surface_return
                groundwater_queue[t+delay[j]] += groundwater_return
                pending += returned
            sector[t, j, 0] = demand[t, j]
            sector[t, j, 1] = allocation[j, 0]
            sector[t, j, 2] = allocation[j, 1]
            sector[t, j, 3] = used
            sector[t, j, 4] = max(0.0, demand[t, j] - supplied)
            sector[t, j, 5] = returned
        surface += immediate_surface
        gw += immediate_groundwater
        late_overflow = max(0.0, gw-gw_capacity)
        gw -= late_overflow
        surface += late_overflow
        storage = gw + reservoir + pending
        error = previous + natural[t] + upstream[t] + recharge[t] - surface - consumed - evap - storage
        daily[t] = np.array([natural[t], upstream[t], recharge[t], surface, sw, pumped,
                            consumed, sector[t, :, 4].sum(), returned_surface+immediate_surface,
                            returned_groundwater+immediate_groundwater, gw, reservoir,
                            pending, evap, max(0.0, env[t]-surface), error,
                            baseflow, overflow+late_overflow, spill, release])
        previous = storage
    return daily, sector


def simulate_water_use(dates, natural_runoff, demands=(), config=None, *, upstream=0.0):
    """Run native managed-water accounting; inputs are m3/day, not m3/s.

    Natural runoff is an external input to this managed-water subsystem.
    Pending returns remain in the final balance instead of disappearing at
    the end of the record. Same-day returns cannot be reused within that day.
    """
    config = config or WaterUseConfig()
    dates = pd.DatetimeIndex(dates).as_unit("ns")
    if len(dates) < 1 or dates.tz is not None or dates.hasnans or (len(dates) > 1 and not np.all(np.diff(dates.asi8) == pd.Timedelta(days=1).value)):
        raise ValueError("Water-use dates must be contiguous timezone-naive daily dates.")
    n = len(dates)
    demands = tuple(demands)
    if len({d.name for d in demands}) != len(demands):
        raise ValueError("Demand names must be unique.")
    demands = tuple(sorted(demands, key=lambda d: d.priority))
    natural = _series(natural_runoff, n, "natural_runoff")
    inflow = _series(upstream, n, "upstream")
    matrix = np.column_stack([_series(d.demand, n, d.name) for d in demands]) if demands else np.empty((n, 0))
    caps = np.column_stack([_series(d.max_withdrawal, n, "max_withdrawal", infinity=True) for d in demands]) if demands else np.empty((n, 0))
    codes = np.array([{"surface": 0, "groundwater": 1, "mixed": 2}[d.source] for d in demands], dtype=np.int64)
    parameters = [np.array([getattr(d, key) for d in demands], dtype=dtype) for key, dtype in
                  [("priority", np.int64), ("consumption_fraction", float), ("groundwater_return_fraction", float), ("return_delay_days", np.int64)]]
    if demands and max(d.return_delay_days for d in demands) > 36500:
        raise ValueError("Return delay cannot exceed 36500 days.")
    env = _series(config.environmental_flow, n, "environmental_flow")
    pump = _series(config.pumping_capacity, n, "pumping_capacity", infinity=True)
    recharge = _series(config.external_recharge, n, "external_recharge")
    release = _series(config.reservoir_release, n, "reservoir_release", infinity=True)
    evap = _series(config.reservoir_evaporation, n, "reservoir_evaporation")
    if config.reservoir_capacity == 0 and np.any(evap):
        raise ValueError("Reservoir evaporation requires a reservoir.")
    # LP receives finite resource availability; pumping/release limits may be inf.
    core, allocator = (_core, _priority) if config.allocation == "priority" else (_core.py_func, _linear)
    daily, sector = core(natural, inflow, matrix, caps, codes, *parameters, env, pump, recharge,
                         config.baseflow_fraction, config.groundwater_recession,
                         config.groundwater_initial, config.groundwater_capacity,
                         config.reservoir_capacity, config.reservoir_initial, release, evap, allocator)
    names = ["natural_runoff", "upstream", "external_recharge", "river_outflow", "surface_withdrawal",
             "groundwater_withdrawal", "consumed", "unmet", "surface_returns", "groundwater_returns",
             "groundwater_storage", "reservoir_storage", "pending_returns", "reservoir_evaporation",
             "environmental_deficit", "balance_error", "groundwater_baseflow",
             "groundwater_spill", "reservoir_spill", "reservoir_release"]
    frame = pd.DataFrame(daily, index=dates, columns=names)
    frame.index.name = "date"
    frame["total_storage"] = frame.groundwater_storage + frame.reservoir_storage + frame.pending_returns
    scale = max(1.0, float(np.max(natural + inflow + recharge)), config.groundwater_initial + config.reservoir_initial,
                float(frame.total_storage.max()))
    if frame.balance_error.abs().max() > 1e-8 * scale:
        raise RuntimeError("Managed-water balance failed; no result accepted.")
    sectors = {d.name: pd.DataFrame(sector[:, j], index=dates, columns=["requested", "surface_withdrawal", "groundwater_withdrawal", "consumed", "unmet", "returns_generated"]) for j, d in enumerate(demands)}
    return WaterUseResult(frame, sectors, config.groundwater_initial + config.reservoir_initial)


def irrigation_demand(pet_mm, precipitation_mm, *, irrigated_area_km2, crop_coefficient=1.0,
                      efficiency=0.7, effective_rainfall_fraction=0.8):
    """Simple climatic gross irrigation demand, m3/day; not a crop/soil model."""
    p, e, coefficient = np.broadcast_arrays(np.asarray(precipitation_mm, dtype=float), np.asarray(pet_mm, dtype=float), np.asarray(crop_coefficient, dtype=float))
    if not np.isfinite(irrigated_area_km2) or irrigated_area_km2 < 0 or not np.isfinite(efficiency) or not 0 < efficiency <= 1 or not np.isfinite(effective_rainfall_fraction) or not 0 <= effective_rainfall_fraction <= 1:
        raise ValueError("Invalid irrigated area, efficiency or rainfall fraction.")
    if any(not np.all(np.isfinite(a)) or np.any(a < 0) for a in (p, e, coefficient)):
        raise ValueError("Rainfall, PET and crop coefficients must be finite and nonnegative.")
    return np.maximum(0, coefficient*e - effective_rainfall_fraction*p) * irrigated_area_km2 * 1000 / efficiency


def domestic_demand(population, *, litres_per_person_day=100.0):
    """Gross household demand in m3/day."""
    population, rate = np.broadcast_arrays(np.asarray(population, dtype=float), np.asarray(litres_per_person_day, dtype=float))
    if any(not np.all(np.isfinite(a)) or np.any(a < 0) for a in (population, rate)):
        raise ValueError("Population and use rate must be finite and nonnegative.")
    return population * rate / 1000


@dataclass(frozen=True)
class WaterUseScenario:
    """Date-aligned demand/configuration for one basin."""
    dates: object
    demands: tuple = ()
    config: WaterUseConfig = field(default_factory=WaterUseConfig)

    def __post_init__(self):
        dates = pd.DatetimeIndex(self.dates).as_unit("ns")
        # Validate/snapshot inputs without executing the model.
        n = len(dates)
        if n < 1 or dates.tz is not None or dates.hasnans or (n > 1 and not np.all(np.diff(dates.asi8) == pd.Timedelta(days=1).value)):
            raise ValueError("Scenario dates must be contiguous daily dates.")
        object.__setattr__(self, "dates", dates)
        object.__setattr__(self, "demands", tuple(replace(d, demand=_series(d.demand, n, d.name), max_withdrawal=_series(d.max_withdrawal, n, "max_withdrawal", infinity=True)) for d in self.demands))
        if len({d.name for d in self.demands}) != len(self.demands):
            raise ValueError("Demand names must be unique.")
        config = self.config
        values = {key: _series(getattr(config, key), n, key, infinity=key in {"pumping_capacity", "reservoir_release"}) for key in ("environmental_flow", "pumping_capacity", "external_recharge", "reservoir_release", "reservoir_evaporation")}
        object.__setattr__(self, "config", replace(config, **values))

    def subset(self, dates):
        index = self.dates.get_indexer(dates)
        # Always start from the same initial state; training is a prefix.
        if not np.array_equal(index, np.arange(len(index))):
            raise ValueError("Managed model requires a scenario-aligned prefix; run continuously from its first date.")
        demands = tuple(replace(d, demand=d.demand[index], max_withdrawal=d.max_withdrawal[index]) for d in self.demands)
        config = replace(self.config, **{key: getattr(self.config, key)[index] for key in ("environmental_flow", "pumping_capacity", "external_recharge", "reservoir_release", "reservoir_evaporation")})
        return demands, config


@dataclass(frozen=True)
class _ManagedRunner:
    base: Model
    scenarios: dict

    def __call__(self, basin, params):
        return self.accounting(basin, params).daily.river_outflow.to_numpy() / (basin.area_km2 * 1000)

    def accounting(self, basin, params):
        if basin.basin_id not in self.scenarios:
            raise ValueError(f"No water-use scenario for basin {basin.basin_id}.")
        demands, config = self.scenarios[basin.basin_id].subset(basin.dates)
        demands = tuple(replace(d, demand=d.demand*params["wu_demand_scale"], consumption_fraction=params["wu_consumption_scale"]*d.consumption_fraction) for d in demands)
        config = replace(config, baseflow_fraction=params["wu_baseflow_fraction"], groundwater_recession=params["wu_groundwater_recession"])
        natural = self.base.simulate(basin, {k: params[k] for k in self.base.defaults}) * basin.area_km2 * 1000
        return simulate_water_use(basin.dates, natural, demands, config)

    def fingerprint(self):
        digest = hashlib.sha256()
        for key, scenario in sorted(self.scenarios.items()):
            digest.update(key.encode())
            digest.update(scenario.dates.asi8.tobytes())
            for obj in (scenario.config, *scenario.demands):
                for name, value in vars(obj).items():
                    digest.update(name.encode())
                    digest.update(value.tobytes() if isinstance(value, np.ndarray) else repr(value).encode())
        return digest.hexdigest()


def managed_model(model="GR4J", *, scenarios):
    """Wrap a daily model for existing calibration, sensitivity and batch APIs.

    Mapping keys are basin IDs. Use a mapping for independent/shared multi-
    basin calibration. Water parameters have the ``wu_`` prefix; use explicit
    calibration bounds/fixed parameters to avoid unidentifiable joint fits.
    """
    base = get_model(model)
    if base.timestep != "daily" or isinstance(base.runner, _ManagedRunner):
        raise ValueError("Wrap an unmodified daily hydrological model.")
    scenarios = dict(scenarios)
    if not scenarios or any(not isinstance(s, WaterUseScenario) for s in scenarios.values()):
        raise ValueError("Provide basin-ID -> WaterUseScenario mapping.")
    # Shared defaults must be explicit rather than silently selecting one basin.
    configs = [s.config for s in scenarios.values()]
    if len({(c.baseflow_fraction, c.groundwater_recession) for c in configs}) != 1:
        raise ValueError("Shared managed-model defaults require matching baseflow fraction and recession.")
    defaults = dict(base.defaults, wu_demand_scale=1.0, wu_consumption_scale=1.0,
                    wu_baseflow_fraction=configs[0].baseflow_fraction,
                    wu_groundwater_recession=configs[0].groundwater_recession)
    bounds = dict(base.bounds, wu_demand_scale=(0.0, 3.0), wu_consumption_scale=(0.0, 1.0),
                  wu_baseflow_fraction=(0.0, 1.0), wu_groundwater_recession=(0.0, 1.0))
    return Model(base.name + "_MANAGED", "daily", defaults, bounds,
                 _ManagedRunner(base, scenarios), base.variant + "; BasinForge conceptual managed-water layer",
                 base.temperature_required, base.backend)


def managed_accounting(basin, model, params=None):
    """Retrieve complete accounting from a managed model, including a fitted one."""
    model = get_model(model)
    if not isinstance(model.runner, _ManagedRunner):
        raise ValueError("model must be created with managed_model.")
    model.validate_basin(basin)
    return model.runner.accounting(basin, model.parameters(params))


def run_water_network(dates, natural_runoff, scenarios, downstream, *, travel_days=None):
    """Route managed outflows through a directed, non-splitting basin network.

    Each basin drains to one other basin or None. Cycles are refused. Natural
    runoff must be local/incremental, not whole-upstream catchment runoff.
    Travel delays are integer days. Unarrived water is reported as final transit.
    """
    keys = set(natural_runoff)
    if not keys or set(scenarios) != keys or set(downstream) != keys:
        raise ValueError("Runoff, scenarios and downstream must name exactly the same basins.")
    travel_days = dict(travel_days or {})
    if set(travel_days)-keys:
        raise ValueError("Unknown travel-days basin.")
    for key, destination in downstream.items():
        lag = travel_days.get(key, 0)
        if destination is not None and destination not in keys:
            raise ValueError("Unknown downstream basin.")
        if not isinstance(lag, int) or isinstance(lag, bool) or lag < 0:
            raise ValueError("Travel days must be nonnegative integers.")
    order, remaining = [], set(keys)
    while remaining:
        ready = sorted(k for k in remaining if not any(downstream[parent] == k for parent in remaining))
        if not ready:
            raise ValueError("Water network contains a cycle.")
        order.extend(ready)
        remaining.difference_update(ready)
    dates = pd.DatetimeIndex(dates).as_unit("ns")
    inflow = {key: np.zeros(len(dates)) for key in keys}
    results, transit = {}, {}
    for key in order:
        demands, config = scenarios[key].subset(dates)
        result = simulate_water_use(dates, natural_runoff[key], demands, config, upstream=inflow[key])
        results[key] = result
        destination = downstream[key]
        if destination is not None:
            lag = travel_days.get(key, 0)
            outflow = result.daily.river_outflow.to_numpy()
            if lag == 0:
                inflow[destination] += outflow
                transit[key] = 0.0
            elif lag < len(dates):
                inflow[destination][lag:] += outflow[:-lag]
                transit[key] = float(outflow[-lag:].sum())
            else:
                transit[key] = float(outflow.sum())
    initial = sum(r.initial_storage for r in results.values())
    inputs = sum(float(r.daily.natural_runoff.sum()+r.daily.external_recharge.sum()) for r in results.values())
    outlet = sum(float(results[k].daily.river_outflow.sum()) for k in keys if downstream[k] is None)
    used = sum(float(r.daily.consumed.sum()+r.daily.reservoir_evaporation.sum()) for r in results.values())
    final = sum(float(r.daily.total_storage.iloc[-1]) for r in results.values()) + sum(transit.values())
    error = initial + inputs - outlet - used - final
    if abs(error) > 1e-8*max(1.0, initial+inputs):
        raise RuntimeError("Network water balance failed.")
    return {"basins": results, "final_transit": transit, "outlet_volume": outlet, "balance_error": error}
