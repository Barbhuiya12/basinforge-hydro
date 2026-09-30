import numpy as np
import pandas as pd
import pytest

from basinforge import Basin, nse, kge, rmse, log_nse
from basinforge.metrics import loss


def test_units_daily_monthly_annual_and_leap_year():
    for step, dates in [("daily", pd.date_range("2020-01-01", periods=2)), ("monthly", pd.date_range("2020-01-01", periods=2, freq="MS")), ("annual", pd.date_range("2020-01-01", periods=2, freq="YS"))]:
        frame = pd.DataFrame({"date": dates, "precipitation": [1, 2], "pet": [1, 1], "qobs": [10, 20]})
        basin = Basin.from_frame(frame, basin_id="B", area_km2=100, timestep=step, q_unit="m3/s")
        np.testing.assert_allclose(basin.to_m3s(basin.qobs), [10, 20])
        if step == "monthly":
            np.testing.assert_array_equal(basin.seconds_per_step / 86400, [31, 29])
        if step == "annual":
            np.testing.assert_array_equal(basin.seconds_per_step / 86400, [366, 365])


def test_gap_and_invalid_forcing_rejection():
    with pytest.raises(ValueError, match="contiguous"):
        Basin("B", pd.to_datetime(["2020-01-01", "2020-01-03"]), [1, 2], [1, 1])
    with pytest.raises(ValueError, match="finite"):
        Basin("B", pd.date_range("2020-01-01", periods=2), [1, np.nan], [1, 1])
    with pytest.raises(ValueError, match="negative"):
        Basin("B", pd.date_range("2020-01-01", periods=2), [-1, 2], [1, 1])


def test_metrics_and_missing_observations():
    obs = np.array([1, 2, 4, np.nan, 3])
    sim = np.array([1, 2, 4, 100, 3])
    assert nse(obs, sim) == 1
    assert kge(obs, sim) == pytest.approx(1)
    assert rmse(obs, sim) == 0
    assert log_nse(obs, sim) == 1
    assert loss(obs, sim, {"nse": .7, "log_nse": .3}) == 0
    with pytest.raises(ValueError, match="constant"):
        nse([1, 1], [1, 2])
    with pytest.raises(ValueError, match="finite"):
        nse([1, 2], [1, np.nan])
    with pytest.raises(ValueError, match="weights"):
        loss([1, 2], [1, 2], {"nse": -1})
