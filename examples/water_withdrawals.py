"""Run a LuMod forcing case study with explicitly assumed water-use scenarios.

Withdrawal assumptions are illustrative, not measured withdrawals from the
LuMod catchment. Optional LuMod is used only to load the example dataset.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import platform
from time import perf_counter

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from basinforge import (WaterDemand, WaterUseConfig, WaterUseScenario,
                       irrigation_demand, domestic_demand, managed_model,
                       managed_accounting, get_model, CalibrationConfig,
                       run_experiment, simulate_water_use, run_water_network,
                       morris_sensitivity, sobol_sensitivity)
from lumod_case_study import load_example


def run(output, *, maxiter=10, samples=100):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    basin = load_example(2)
    # These quantities are assumed, deliberately not inferred from outlet flow.
    irrigation = irrigation_demand(basin.pet, basin.precipitation,
        irrigated_area_km2=basin.area_km2*.05, efficiency=.7)
    demands = (WaterDemand("domestic", domestic_demand(10000), source="surface", priority=0, consumption_fraction=.2),
               WaterDemand("irrigation_surface", irrigation*.6, source="surface", priority=1, consumption_fraction=.7,
                           groundwater_return_fraction=.5, return_delay_days=7),
               WaterDemand("irrigation_groundwater", irrigation*.4, source="groundwater", priority=1, consumption_fraction=.7,
                           groundwater_return_fraction=.5, return_delay_days=7),
               WaterDemand("industry", 500, source="surface", priority=2, consumption_fraction=.25, return_delay_days=2))
    config = WaterUseConfig(baseflow_fraction=.2, groundwater_recession=.03,
                           groundwater_initial=basin.area_km2*1000*10,
                           pumping_capacity=20000, environmental_flow=2000)
    scenario = WaterUseScenario(basin.dates, demands, config)
    model = managed_model(scenarios={basin.basin_id: scenario})
    # Fit hydrological parameters only; water-use assumptions remain fixed.
    # This avoids claiming outlet flow identifies actual withdrawals.
    calibration = CalibrationConfig(warmup=365, calibration_fraction=.7,
        maxiter=maxiter, popsize=5, samples=samples, bounds=get_model("GR4J").bounds)
    studies = {}
    for method in ("de", "lhs", "multistart"):
        studies[method] = run_experiment(basin, model, replace(calibration, method="lhs" if method == "lhs" else "de"),
            starts=2 if method == "multistart" else 1,
            sensitivity="morris", sensitivity_options={"trajectories": 4}, output=output/method)
    fitted = studies["de"]["fit"].parameters
    water_config = replace(calibration, fixed={k: fitted[k] for k in get_model("GR4J").defaults},
        bounds={"wu_demand_scale": (.5, 1.5), "wu_consumption_scale": (.5, 1),
                "wu_baseflow_fraction": (.1, .3), "wu_groundwater_recession": (.01, .1)})
    water_sensitivity = {"morris": morris_sensitivity(basin, model, water_config, trajectories=8),
                         "sobol": sobol_sensitivity(basin, model, water_config, samples=64, bootstrap=50)}
    with (output/"water-sensitivity.json").open("x") as stream:
        json.dump(water_sensitivity, stream, indent=2, allow_nan=False)
    result = managed_accounting(basin, model, fitted)
    natural = get_model("GR4J").simulate(basin, {k: fitted[k] for k in get_model("GR4J").defaults}) * basin.area_km2*1000
    # Compare native priority and LP on the same forcing/parameter scenario.
    start = perf_counter()
    priority = simulate_water_use(basin.dates, natural, demands, config)
    priority_seconds = perf_counter()-start
    short = min(365, len(basin.dates))
    start = perf_counter()
    lp = simulate_water_use(basin.dates[:short], natural[:short],
        tuple(replace(d, demand=np.asarray(d.demand)[:short] if np.asarray(d.demand).ndim else d.demand) for d in demands),
        replace(config, allocation="lp"))
    lp_seconds = perf_counter()-start
    lp.daily.to_csv(output/"lp-first-year-water-balance.csv")
    network = run_water_network(basin.dates, {"upstream": natural*.4, "downstream": natural*.6},
        {"upstream": WaterUseScenario(basin.dates), "downstream": scenario},
        {"upstream": "downstream", "downstream": None}, travel_days={"upstream": 1})
    for key, accounting in network["basins"].items():
        accounting.daily.to_csv(output/f"network-{key}.csv")
    figure = Figure(figsize=(12, 8), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(3, 1)
    count = min(365, len(basin.dates))
    axes[0].plot(basin.dates[:count], natural[:count]/86400, label="Natural-model scenario", color="#64748b")
    axes[0].plot(basin.dates[:count], result.daily.river_outflow.iloc[:count]/86400, label="Managed scenario", color="#087e8b")
    axes[0].set(ylabel="Discharge (m³/s)", title="LuMod example 2 forcings · assumed water use · first year")
    axes[0].legend()
    for name, accounting in result.sectors.items():
        axes[1].plot(basin.dates[:count], (accounting.surface_withdrawal+accounting.groundwater_withdrawal).iloc[:count], label=name)
    axes[1].set(ylabel="Withdrawal (m³/day)")
    axes[1].legend()
    axes[2].plot(basin.dates[:count], result.daily.groundwater_storage.iloc[:count], label="Conceptual groundwater")
    axes[2].plot(basin.dates[:count], result.daily.pending_returns.iloc[:count], label="Pending returns")
    axes[2].set(ylabel="Storage (m³)")
    axes[2].legend()
    figure.savefig(output/"water-use-scenario.png", dpi=150)
    metadata = {"dataset": "LuMod example 2", "water_use": "Assumed scenario, not observed withdrawals",
        "assumptions": {"population": 10000, "irrigated_area_fraction": .05, "irrigation_groundwater_demand_fraction": .4, "industrial_m3_day": 500,
                        "groundwater_initial_mm": 10, "baseflow_fraction": .2, "groundwater_recession_day": .03,
                        "environmental_m3_day": 2000, "pumping_capacity_m3_day": 20000},
        "calibration": {"warmup": 365, "training_fraction": .7, "maxiter": maxiter,
                        "popsize": 5, "lhs_samples": samples, "seed": 42, "multistart_seeds": [42, 43]},
        "priority": priority.summary(), "lp_first_year": lp.summary(),
        "network_balance_error_m3": network["balance_error"], "network_final_transit_m3": network["final_transit"],
        "timing": {"priority_days": len(basin.dates), "priority_seconds": priority_seconds,
                   "lp_days": short, "lp_seconds": lp_seconds, "platform": platform.platform(),
                   "note": "Single local run; priority compiled kernel was warmed by calibration. LP uses Python/HiGHS; differing time spans are reported explicitly."},
        "fits": {method: {"calibration": study["fit"].calibration_metrics, "validation": study["fit"].validation_metrics} for method, study in studies.items()}}
    with (output/"scenario.json").open("x") as stream:
        json.dump(metadata, stream, indent=2, allow_nan=False)
    print(json.dumps(metadata, indent=2, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("water-use-study"))
    parser.add_argument("--maxiter", type=int, default=10)
    parser.add_argument("--samples", type=int, default=100)
    args = parser.parse_args()
    run(args.output, maxiter=args.maxiter, samples=args.samples)
