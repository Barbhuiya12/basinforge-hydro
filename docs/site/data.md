# Input data

## Time-series CSV

```text
date,precipitation,pet,qobs,temperature
```

| Field | Meaning | Units / requirements |
| --- | --- | --- |
| date | Model time step | Unique, increasing and continuous dates |
| precipitation | Precipitation total | Nonnegative mm per model step |
| pet | Potential evapotranspiration | Nonnegative mm per model step |
| qobs | Observed discharge | Explicitly select mm per step or m³/s |
| temperature | Mean temperature | °C; required by temperature-dependent models |

`qobs` is optional for simulation and required for calibration. Missing observations may be NaN; missing forcing steps must not be dropped or silently filled. P, PET and any required temperature must be finite.

## Load a basin

```python
from basinforge import Basin

basin = Basin.from_csv(
    "basin.csv", basin_id="catchment-A",
    area_km2=1200, q_unit="m3/s", timestep="daily",
)
```

The filename and area illustrate the schema, not supplied observations or a verified catchment area. Area must be in km² and is needed for discharge conversion.

Existing column names can be mapped:

```python
basin = Basin.from_frame(
    frame, basin_id="catchment-A", area_km2=1200,
    columns={"prec": "precipitation", "qt": "qobs", "tmean": "temperature"},
    q_unit="m3/s", timestep="daily",
)
```

## Model frequency

GR2M and ABCD require monthly inputs; GR1A requires annual inputs. Other currently registered implementations use daily inputs. Monthly and annual series are never automatically treated as daily data. Supply appropriately aggregated forcing and observations.

Warmup is a **count of model steps**. The default 365 is daily-oriented and must be changed for monthly or annual models.

## Discharge conversion

Simulation outputs are mm per model step. Conversion to m³/s uses basin area and the actual time-step duration, including differing month lengths and leap years.

```python
q_m3s = basin.to_m3s(q_mm)
```

## Multi-basin manifest

```text
basin_id,path,area_km2,latitude,timestep,q_unit
catchment-A,data/a.csv,1200,32,daily,m3/s
catchment-B,data/b.csv,800,32,daily,m3/s
```

Paths are relative to the manifest. These are schema examples, not real basin metadata. See [Multi-basin workflows](multi-basin.md).
