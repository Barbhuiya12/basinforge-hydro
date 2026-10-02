from dataclasses import replace
import pickle

import numpy as np
import pandas as pd
import pytest

from basinforge import (WaterDemand, WaterUseConfig, WaterUseScenario,
                       simulate_water_use, managed_model, managed_accounting,
                       run_water_network, irrigation_demand, domestic_demand,
                       CalibrationConfig, calibrate, calibrate_many, calibrate_shared,
                       run_experiment, get_model, list_models, sobol_sensitivity)
from basinforge.calibration import fingerprint
from test_models import make_basin


def dates(n=5):
    return pd.date_range("2000-01-01", periods=n)


@pytest.mark.parametrize("allocation", ["priority", "lp"])
def test_no_demands_is_identity(allocation):
    result = simulate_water_use(dates(), np.arange(5), config=WaterUseConfig(allocation=allocation))
    np.testing.assert_array_equal(result.daily.river_outflow, np.arange(5))
    assert result.balance_error == 0


@pytest.mark.parametrize("allocation", ["priority", "lp"])
def test_priority_environment_and_unmet(allocation):
    demands = [WaterDemand("industry", 60, source="surface", priority=2, consumption_fraction=1),
               WaterDemand("domestic", 30, source="surface", priority=1, consumption_fraction=1)]
    result = simulate_water_use(dates(), 100, demands, WaterUseConfig(allocation=allocation, environmental_flow=20))
    np.testing.assert_allclose(result.sectors["domestic"].surface_withdrawal, 30)
    np.testing.assert_allclose(result.sectors["industry"].surface_withdrawal, 50)
    np.testing.assert_allclose(result.daily.river_outflow, 20)
    np.testing.assert_allclose(result.daily.unmet, 10)
    assert result.balance_error < 1e-8


@pytest.mark.parametrize("allocation", ["priority", "lp"])
def test_pumping_recharge_and_delayed_returns(allocation):
    result = simulate_water_use(dates(3), 0,
             [WaterDemand("pump", 10, source="groundwater", consumption_fraction=.2,
                          groundwater_return_fraction=.5, return_delay_days=2)],
             WaterUseConfig(allocation=allocation, groundwater_initial=30, pumping_capacity=10))
    np.testing.assert_allclose(result.daily.groundwater_withdrawal, [10, 10, 10])
    np.testing.assert_allclose(result.daily.groundwater_storage, [20, 10, 4])
    np.testing.assert_allclose(result.daily.river_outflow, [0, 0, 4])
    np.testing.assert_allclose(result.daily.pending_returns, [8, 16, 16])
    assert result.balance_error < 1e-8


def test_pumping_reduces_baseflow_without_double_counting():
    config = WaterUseConfig(baseflow_fraction=1, groundwater_recession=.5)
    natural = np.array([100., 0, 0, 0, 0])
    baseline = simulate_water_use(dates(), natural, config=config)
    pumped = simulate_water_use(dates(), natural, [WaterDemand("well", [50, 0, 0, 0, 0], source="groundwater", consumption_fraction=1)], config)
    assert baseline.daily.river_outflow.sum() + baseline.daily.total_storage.iloc[-1] == 100
    np.testing.assert_allclose(pumped.daily.river_outflow, baseline.daily.river_outflow / 2)
    assert pumped.balance_error == 0


@pytest.mark.parametrize("allocation", ["priority", "lp"])
def test_pumping_reserves_today_environmental_baseflow(allocation):
    result = simulate_water_use(dates(1), 0, [WaterDemand("well", 100, source="groundwater", consumption_fraction=1)],
              WaterUseConfig(allocation=allocation, groundwater_initial=100,
                             groundwater_recession=.5, environmental_flow=20))
    np.testing.assert_allclose(result.daily.groundwater_withdrawal, [60])
    np.testing.assert_allclose(result.daily.groundwater_baseflow, [20])
    np.testing.assert_allclose(result.daily.environmental_deficit, [0])


def test_immediate_returns_not_reallocated_same_day():
    result = simulate_water_use(dates(2), [10, 0],
             [WaterDemand("first", 10, priority=1, consumption_fraction=0, return_delay_days=0),
              WaterDemand("second", 10, priority=2, consumption_fraction=1)])
    np.testing.assert_array_equal(result.daily.river_outflow, [10, 0])
    np.testing.assert_array_equal(result.sectors["second"].unmet, [10, 10])
    assert result.balance_error == 0


@pytest.mark.parametrize("allocation", ["priority", "lp"])
def test_reservoir_capacity_release_evaporation(allocation):
    result = simulate_water_use(dates(3), [100, 0, 0], config=WaterUseConfig(
        allocation=allocation, reservoir_capacity=80, reservoir_release=10, reservoir_evaporation=5))
    np.testing.assert_array_equal(result.daily.river_outflow, [25, 10, 10])
    np.testing.assert_array_equal(result.daily.reservoir_storage, [70, 55, 40])
    assert result.balance_error == 0


def test_climatic_demand_units_and_validation():
    np.testing.assert_allclose(irrigation_demand([5, 2], [0, 10], irrigated_area_km2=2, efficiency=.5), [20000, 0])
    assert domestic_demand(1000, litres_per_person_day=100) == 100
    with pytest.raises(ValueError):
        irrigation_demand([1], [1], irrigated_area_km2=2, efficiency=0)
    with pytest.raises(ValueError):
        domestic_demand(-1)


@pytest.mark.parametrize("allocation", ["priority", "lp"])
def test_randomized_water_balance(allocation):
    rng = np.random.default_rng(42)
    for trial in range(5):
        n = 25
        demands = [WaterDemand(str(j), rng.uniform(0, 100, n), source=source,
                   priority=j % 2, consumption_fraction=rng.random(),
                   groundwater_return_fraction=rng.random(), return_delay_days=j,
                   max_withdrawal=80) for j, source in enumerate(["mixed", "surface", "groundwater"])]
        result = simulate_water_use(dates(n), rng.uniform(0, 200, n), demands,
            WaterUseConfig(allocation=allocation, baseflow_fraction=.3, groundwater_recession=.1,
                           groundwater_initial=70, groundwater_capacity=200,
                           reservoir_capacity=100, reservoir_initial=20, reservoir_release=75,
                           pumping_capacity=25, reservoir_evaporation=3, external_recharge=5,
                           environmental_flow=10))
        assert result.balance_error < 1e-7
        assert np.all(result.daily.drop(columns="balance_error") >= -1e-8)
        assert np.max(result.daily.groundwater_storage) <= 200 + 1e-8
        assert np.max(result.daily.reservoir_storage) <= 100 + 1e-8
        assert np.max(result.daily.groundwater_withdrawal) <= 25 + 1e-7


def test_lp_preserves_surface_for_surface_only_user():
    demands = [WaterDemand("mixed", 10, consumption_fraction=1),
               WaterDemand("surface", 10, source="surface", consumption_fraction=1)]
    config = WaterUseConfig(groundwater_initial=10)
    greedy = simulate_water_use(dates(1), 10, demands, config)
    optimal = simulate_water_use(dates(1), 10, demands, replace(config, allocation="lp"))
    assert greedy.daily.unmet.iloc[0] == 10
    assert optimal.daily.unmet.iloc[0] == 0
    assert optimal.balance_error < 1e-8


def test_network_delayed_routing_mass_balance_and_cycles():
    scenario = WaterUseScenario(dates())
    result = run_water_network(dates(), {"A": np.ones(5)*10, "B": np.ones(5)*2},
        {"A": scenario, "B": scenario}, {"A": "B", "B": None}, travel_days={"A": 2})
    np.testing.assert_array_equal(result["basins"]["B"].daily.river_outflow, [2, 2, 12, 12, 12])
    assert result["final_transit"]["A"] == 20
    assert result["balance_error"] == 0
    with pytest.raises(ValueError, match="cycle"):
        run_water_network(dates(), {"A": 10, "B": 2}, {"A": scenario, "B": scenario}, {"A": "B", "B": "A"})


def setup_managed(identifier="fixture"):
    basin = make_basin(n=100, identifier=identifier)
    scenario = WaterUseScenario(basin.dates, (WaterDemand("domestic", 10000, source="surface", consumption_fraction=1),))
    model = managed_model(scenarios={identifier: scenario})
    basin = replace(basin, qobs=model.simulate(basin, {"wu_demand_scale": 1.3}))
    return basin, model, scenario


def test_managed_joint_calibration_sensitivity_export(tmp_path):
    basin, model, _ = setup_managed()
    config = CalibrationConfig(method="lhs", samples=20, warmup=10, calibration_fraction=.7,
                               bounds={"wu_demand_scale": (.5, 2)})
    study = run_experiment(basin, model, config, sensitivity_options={"trajectories": 3}, output=tmp_path/"study")
    assert abs(study["fit"].parameters["wu_demand_scale"]-1.3) < .1
    assert study["sensitivity"]["parameters"][0]["parameter"] == "wu_demand_scale"
    np.testing.assert_allclose(study["fit"].simulated, managed_accounting(basin, model, study["fit"].parameters).daily.river_outflow / (basin.area_km2*1000))
    assert (tmp_path/"study"/"report"/"index.html").is_file()
    assert (tmp_path/"study"/"water-balance.csv").is_file()
    assert (tmp_path/"study"/"water-sectors.csv").is_file()
    restored = pickle.loads(pickle.dumps(model))
    np.testing.assert_array_equal(restored.simulate(basin), model.simulate(basin))


def test_scenario_snapshot_prefix_and_resume_fingerprint():
    basin, model, scenario = setup_managed()
    with pytest.raises(ValueError, match="prefix"):
        scenario.subset(basin.dates[1:])
    assert not scenario.demands[0].demand.flags.writeable
    changed = managed_model(scenarios={basin.basin_id: replace(scenario, demands=(WaterDemand("domestic", 20000),))})
    assert fingerprint(basin, model, CalibrationConfig()) != fingerprint(basin, changed, CalibrationConfig())


def test_managed_validation_data_cannot_change_fit():
    basin, model, _ = setup_managed()
    config = CalibrationConfig(method="lhs", samples=8, warmup=10, calibration_fraction=.7,
                               bounds={"wu_demand_scale": (.5, 2)})
    changed = basin.qobs.copy()
    changed[70:] *= 100
    first = calibrate(basin, model, config)
    second = calibrate(replace(basin, qobs=changed), model, config)
    assert first.parameters == second.parameters
    assert first.objective_loss == second.objective_loss
    sensitivity = sobol_sensitivity(basin, model, config, samples=16, bootstrap=10)
    assert sensitivity["evaluations"] == 48
    assert np.isfinite(sensitivity["parameters"][0]["total_order"])


@pytest.mark.parametrize("name", [item["name"] for item in list_models() if item["timestep"] == "daily"])
def test_managed_wrapper_all_native_daily_models(name):
    basin = make_basin(name)
    model = managed_model(name, scenarios={basin.basin_id: WaterUseScenario(basin.dates)})
    np.testing.assert_allclose(model.simulate(basin), get_model(name).simulate(basin))


def test_long_delay_retained_and_groundwater_overflow():
    result = simulate_water_use(dates(2), 10,
        [WaterDemand("irrigation", 5, source="surface", consumption_fraction=0, return_delay_days=365)],
        WaterUseConfig(baseflow_fraction=.5, groundwater_capacity=1))
    np.testing.assert_array_equal(result.daily.pending_returns, [5, 10])
    np.testing.assert_array_equal(result.daily.groundwater_storage, [1, 1])
    assert result.balance_error == 0


def test_resume_refuses_changed_water_scenario(tmp_path):
    basin, model, scenario = setup_managed()
    config = CalibrationConfig(method="lhs", samples=5, warmup=10, bounds={"wu_demand_scale": (.5, 2)})
    calibrate_many([basin], model, config, output=tmp_path/"results")
    changed = managed_model(scenarios={basin.basin_id: replace(scenario, demands=(WaterDemand("domestic", 20000),))})
    resumed = calibrate_many([basin], changed, config, output=tmp_path/"results", resume=True)
    assert "different data" in resumed["errors"][basin.basin_id]


def test_independent_and_shared_multibasin():
    a, _, sa = setup_managed("A")
    b, _, sb = setup_managed("B")
    model = managed_model(scenarios={"A": sa, "B": sb})
    config = CalibrationConfig(method="lhs", samples=5, warmup=10, bounds={"wu_demand_scale": (.5, 2)})
    serial = calibrate_many([a, b], model, config)
    parallel = calibrate_many([a, b], model, config, workers=2)
    assert serial["errors"] == parallel["errors"] == {}
    assert serial["results"]["A"].parameters == parallel["results"]["A"].parameters
    shared = calibrate_shared([a, b], model, config)
    assert set(shared["basins"]) == {"A", "B"}


@pytest.mark.parametrize("kwargs", [{"consumption_fraction": 2}, {"return_delay_days": -1}, {"source": "invalid"}, {"priority": True}])
def test_invalid_demand(kwargs):
    with pytest.raises(ValueError):
        WaterDemand("x", 1, **kwargs)


@pytest.mark.parametrize("kwargs", [{"groundwater_initial": -1}, {"groundwater_capacity": -1}, {"reservoir_initial": 1}, {"baseflow_fraction": np.nan}, {"allocation": "unknown"}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        WaterUseConfig(**kwargs)


@pytest.mark.parametrize("runoff", [[1, 2], np.nan, -1, np.inf])
def test_invalid_runoff(runoff):
    with pytest.raises(ValueError):
        simulate_water_use(dates(), runoff)


def test_invalid_dates_and_monthly_wrapper():
    with pytest.raises(ValueError):
        simulate_water_use(pd.to_datetime(["2000-01-01", "2000-01-03"]), 1)
    with pytest.raises(ValueError):
        managed_model("GR2M", scenarios={"A": WaterUseScenario(dates())})
