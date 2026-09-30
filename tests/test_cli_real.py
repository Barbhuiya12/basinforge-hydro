import json
import sys

import numpy as np
import pandas as pd
import pytest

from basinforge import Basin, CalibrationConfig, calibrate
from basinforge.cli import main
from test_calibration import observed


def test_real_lumod_record_calibrates_and_validates():
    import lumod
    info, frame = lumod.load_example(2)
    pet = lumod.models.GR4J(area=float(info.area), lat=float(info.lat)).run(frame).pet
    frame = frame.assign(pet=pet)
    basin = Basin.from_frame(frame, basin_id="real-lumod-2", area_km2=float(info.area), latitude=float(info.lat), columns={"prec": "precipitation", "qt": "qobs", "tmean": "temperature"}, q_unit="m3/s")
    fit = calibrate(basin, config=CalibrationConfig(warmup=365, calibration_fraction=0.7, maxiter=1, popsize=5))
    assert len(fit.simulated) == 3287
    assert np.isfinite(fit.objective_loss)
    assert fit.validation_metrics is not None
    assert np.isfinite(fit.validation_metrics["nse"])


def test_cli_simulation_fit_and_no_overwrite(tmp_path, monkeypatch, capsys):
    basin = observed()
    source = tmp_path / "basin.csv"
    pd.DataFrame({"date": basin.dates, "precipitation": basin.precipitation, "pet": basin.pet, "qobs": basin.qobs}).to_csv(source, index=False)
    output = tmp_path / "simulation.csv"
    command = ["basinforge", "run", str(source), "--area", "150", "--output", str(output)]
    monkeypatch.setattr(sys, "argv", command)
    main()
    simulation = pd.read_csv(output)
    assert len(simulation) == len(basin.dates)
    np.testing.assert_allclose(simulation.qsim_m3s, basin.to_m3s(simulation.qsim_mm))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    fit_path = tmp_path / "fit"
    monkeypatch.setattr(sys, "argv", ["basinforge", "calibrate", str(source), "--area", "150", "--warmup", "10", "--calibration-fraction", "0.7", "--maxiter", "0", "--output", str(fit_path)])
    main()
    metadata = json.loads((fit_path / "fit.json").read_text())
    assert metadata["config"]["calibration_fraction"] == 0.7
    assert metadata["validation_metrics"] is not None
    assert (fit_path / "simulation.csv").exists()


def test_cli_actual_models(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["basinforge", "models"])
    main()
    assert len(json.loads(capsys.readouterr().out)) == 14


def test_cli_optional_inventory_and_doctor(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["basinforge", "models", "--all"])
    main()
    assert len(json.loads(capsys.readouterr().out)) == 61
    monkeypatch.setattr(sys, "argv", ["basinforge", "doctor"])
    main()
    description = json.loads(capsys.readouterr().out)
    assert description["python_adapters"] == 14
    assert description["optional_octave_adapters"] == 47
    assert "marrmot" not in description  # no runtime invocation implied


def test_cli_multistart_with_report(tmp_path, monkeypatch, capsys):
    basin = observed()
    source = tmp_path / "basin.csv"
    pd.DataFrame({"date": basin.dates, "precipitation": basin.precipitation, "pet": basin.pet, "qobs": basin.qobs}).to_csv(source, index=False)
    output = tmp_path / "multi"
    monkeypatch.setattr(sys, "argv", ["basinforge", "calibrate", str(source), "--area", "150", "--warmup", "10", "--calibration-fraction", ".7", "--maxiter", "0", "--starts", "2", "--report", "--output", str(output)])
    main()
    trials = json.loads((output / "multistart.json").read_text())["trials"]
    best = json.loads((output / "fit.json").read_text())
    assert len(trials) == 2
    assert best["objective_loss"] == min(fit["objective_loss"] for fit in trials)
    assert (output / "report" / "index.html").exists()
