from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Basin:
    """Contiguous forcing record; P/PET/Q are depths per model time step."""
    basin_id: str
    dates: pd.DatetimeIndex
    precipitation: np.ndarray
    pet: np.ndarray
    qobs: np.ndarray | None = None
    temperature: np.ndarray | None = None
    area_km2: float = 100.0
    latitude: float = 0.0
    timestep: str = "daily"

    def __post_init__(self):
        if not isinstance(self.basin_id, str) or not self.basin_id.strip() or not np.isfinite(self.area_km2) or self.area_km2 <= 0:
            raise ValueError("Basin ID and positive finite area_km2 are required.")
        if not np.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("Latitude must be within [-90, 90].")
        dates = pd.DatetimeIndex(self.dates).as_unit("ns")
        if dates.tz is not None or dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing or len(dates) < 2:
            raise ValueError("Dates must be timezone-naive, unique, increasing, with at least two time steps.")
        if self.timestep == "daily":
            regular = bool(np.all(np.diff(dates.asi8) == pd.Timedelta(days=1).value))
        elif self.timestep in {"monthly", "annual"}:
            periods = dates.to_period("M" if self.timestep == "monthly" else "Y")
            regular = bool(np.all(np.diff(periods.asi8) == 1))
        else:
            raise ValueError("timestep must be daily, monthly, or annual.")
        if not regular:
            raise ValueError("Forcing dates must be contiguous at the selected time step. Do not drop missing days.")
        object.__setattr__(self, "dates", dates)
        for name in ["precipitation", "pet", "qobs", "temperature"]:
            value = getattr(self, name)
            if value is None:
                if name in {"precipitation", "pet"}:
                    raise ValueError(f"{name} is required.")
                continue
            array = np.array(value, dtype=np.float64, order="C", copy=True)
            if array.ndim != 1 or len(array) != len(dates):
                raise ValueError(f"{name} must have one value per date.")
            if name == "qobs":
                if np.any(np.isinf(array)) or np.any(array[np.isfinite(array)] < 0):
                    raise ValueError("Observed discharge must be nonnegative; missing observations may be NaN.")
            elif not np.all(np.isfinite(array)):
                raise ValueError(f"{name} must be finite at every time step.")
            if name in {"precipitation", "pet"} and np.any(array < 0):
                raise ValueError(f"{name} cannot be negative.")
            array.flags.writeable = False
            object.__setattr__(self, name, array)

    @property
    def seconds_per_step(self):
        if self.timestep == "daily":
            days = np.ones(len(self.dates))
        elif self.timestep == "monthly":
            days = self.dates.days_in_month.to_numpy()
        else:
            days = np.where(self.dates.is_leap_year, 366, 365)
        return days * 86400.0

    def to_m3s(self, depths):
        return np.asarray(depths) * self.area_km2 * 1000 / self.seconds_per_step

    @classmethod
    def from_frame(cls, frame, *, basin_id, area_km2, latitude=0, timestep="daily", q_unit="mm", columns=None):
        # Canonical columns: date, precipitation, pet, qobs, temperature.
        frame = frame.rename(columns=columns or {}).copy()
        dates = pd.DatetimeIndex(pd.to_datetime(frame["date"])) if "date" in frame else pd.DatetimeIndex(frame.index)
        if not isinstance(frame.index, pd.DatetimeIndex) and "date" not in frame:
            raise ValueError("Supply a date column or a DatetimeIndex.")
        basin = cls(str(basin_id), dates, frame["precipitation"].to_numpy(), frame["pet"].to_numpy(), frame["qobs"].to_numpy() if "qobs" in frame else None, frame["temperature"].to_numpy() if "temperature" in frame else None, area_km2, latitude, timestep)
        if q_unit not in {"mm", "m3/s"}:
            raise ValueError("q_unit must be 'mm' per time step or 'm3/s'.")
        if q_unit == "m3/s" and basin.qobs is not None:
            from dataclasses import replace
            basin = replace(basin, qobs=basin.qobs * basin.seconds_per_step / (area_km2 * 1000))
        return basin

    @classmethod
    def from_csv(cls, path: str | Path, **kwargs):
        return cls.from_frame(pd.read_csv(path), **kwargs)
