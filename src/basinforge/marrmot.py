"""Persistent Octave adapter to all 47 pinned MARRMoT v2 structures.

The external runtime is optional. Original equations/solvers remain in the
vendored GPL .m files; these variants are not the original named models.
"""
from __future__ import annotations

import atexit
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from multiprocessing.util import Finalize

import numpy as np
from scipy.io import loadmat, savemat


SOURCE = Path(__file__).parent / "_vendor" / "marrmot"
MANIFEST = Path(__file__).parent / "marrmot_manifest.json"


class EngineUnavailableError(RuntimeError):
    """External scientific engine or its prerequisites could not start."""


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


class _Session:
    def __init__(self, executable, package_list, timeout):
        executable = shutil.which(executable) or (str(Path(executable).resolve()) if Path(executable).is_file() else None)
        if executable is None:
            raise EngineUnavailableError("MARRMoT requires octave-cli and Octave's optim package. Install them or call configure_marrmot(octave='/path/to/octave-cli', package_list='/path/to/local-list').")
        self.timeout = timeout
        self.workspace = tempfile.TemporaryDirectory(prefix="basinforge-marrmot-")
        self.directory = Path(self.workspace.name)
        self.forcing_owner = None
        self.diagnostic = []
        self.lock = threading.Lock()
        # Relocated conda Octave needs its own prefix variables. Do not alter
        # HOME or the caller's environment. No user startup files/history.
        environment = os.environ.copy()
        prefix = Path(executable).resolve().parent.parent
        if (prefix / "share" / "octave").is_dir():
            environment["OCTAVE_HOME"] = str(prefix)
            environment["OCTAVE_EXEC_HOME"] = str(prefix)
        worker = Path(__file__).parent
        expression = f"addpath({_quote(worker)}); marrmot_worker({_quote(SOURCE)}, {_quote(package_list or '')}, {_quote(self.directory)});"
        self.process = subprocess.Popen([executable, "--norc", "--no-history", "--quiet", "--eval", expression], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment)
        # Drain warnings so verbose numerical solves cannot fill the pipe.
        def drain():
            for line in self.process.stdout:
                self.diagnostic.append(line.decode(errors="replace").strip())
                self.diagnostic[:] = self.diagnostic[-20:]
        self.reader = threading.Thread(target=drain, daemon=True)
        self.reader.start()

    def request(self, value):
        if self.process.poll() is not None:
            raise EngineUnavailableError(f"Octave exited with code {self.process.returncode}.")
        request_file = self.directory / "request.json"
        response_file = self.directory / "response.json"
        response_file.unlink(missing_ok=True)
        pending = self.directory / "request.tmp"
        pending.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
        pending.replace(request_file)
        deadline = time.monotonic() + self.timeout
        while True:
            if response_file.exists():
                response = json.loads(response_file.read_text())
                if not response["ok"]:
                    raise RuntimeError(f"MARRMoT engine: {response['error']}")
                return response
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close()
                raise EngineUnavailableError(f"Octave request timed out after {self.timeout}s; process stopped.")
            if self.process.poll() is not None:
                self.close()
                raise EngineUnavailableError("Octave stopped: " + "\n".join(self.diagnostic))
            time.sleep(min(0.002, remaining))

    def run(self, basin, class_name, theta, s0, *, details=True):
        with self.lock:
            source = self.directory / "forcing.mat"
            target = self.directory / "output.mat"
            if self.forcing_owner is not basin:
                temperature = basin.temperature if basin.temperature is not None else np.zeros(len(basin.dates))
                savemat(source, {"forcing": np.column_stack((basin.precipitation, basin.pet, temperature))})
                # Retain the owner: an object ID alone can be reused.
                self.forcing_owner = basin
            self.request({"op": "run", "class_name": class_name, "input_file": str(source), "output_file": str(target), "theta": theta, "s0": s0, "details": details})
            output = loadmat(target, simplify_cells=True)
            result = {"qsim_mm": np.asarray(output["q"], dtype=float).reshape(-1)}
            if details:
                result.update(actual_evaporation_mm=np.asarray(output["ea"], dtype=float).reshape(-1), stores_mm=output["stores"], solver_residuals=np.asarray(output["residuals"], dtype=float).reshape(-1), water_balance_error_mm=float(output["water_balance"]))
            return result

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.reader.join(timeout=2)
        for stream in [self.process.stdout]:
            if stream:
                stream.close()
        self.workspace.cleanup()


_SESSIONS = {}
_SESSIONS_LOCK = threading.Lock()
_FINALIZER_PIDS = set()


def _session(executable=None, package_list=None, timeout=300):
    executable = executable or os.environ.get("BASINFORGE_OCTAVE", "octave-cli")
    package_list = package_list or os.environ.get("BASINFORGE_OCTAVE_PACKAGE_LIST")
    key = (os.getpid(), executable, package_list, timeout)
    with _SESSIONS_LOCK:
        current = _SESSIONS.get(key)
        if current is None or current.process.poll() is not None:
            if current is not None:
                current.close()
            current = _SESSIONS[key] = _Session(executable, package_list, timeout)
            if os.getpid() not in _FINALIZER_PIDS:
                # Spawned pool workers do not necessarily execute atexit.
                Finalize(None, close_marrmot, exitpriority=10)
                _FINALIZER_PIDS.add(os.getpid())
    return current


def close_marrmot():
    """Release only Octave workers owned by this Python process."""
    with _SESSIONS_LOCK:
        for key, session in list(_SESSIONS.items()):
            if key[0] == os.getpid():
                session.close()
                del _SESSIONS[key]


atexit.register(close_marrmot)


@dataclass(frozen=True)
class MarrmotRunner:
    class_name: str
    parameter_count: int
    store_count: int
    executable: str | None = None
    package_list: str | None = None
    timeout: float = 300

    def details(self, basin, parameters):
        theta = [parameters[f"p{i:02d}"] for i in range(1, self.parameter_count + 1)]
        states = [parameters[f"s{i:02d}"] for i in range(1, self.store_count + 1)]
        return _session(self.executable, self.package_list, self.timeout).run(basin, self.class_name, theta, states)

    def __call__(self, basin, parameters):
        theta = [parameters[f"p{i:02d}"] for i in range(1, self.parameter_count + 1)]
        states = [parameters[f"s{i:02d}"] for i in range(1, self.store_count + 1)]
        q = _session(self.executable, self.package_list, self.timeout).run(basin, self.class_name, theta, states, details=False)["qsim_mm"]
        # Remove only sub-1e-8 mm solver roundoff. Material negatives still
        # fail validation. details() deliberately retains raw outputs.
        q[(q < 0) & (q >= -1e-8)] = 0.0
        return q


def marrmot_registry():
    from .models import Model
    entries = json.loads(MANIFEST.read_text())
    models = {}
    for entry in entries:
        name = "MARRMOT_" + entry["class_name"].split("_")[1]
        bounds = {f"p{i:02d}": tuple(pair) for i, pair in enumerate(entry["bounds"], 1)}
        defaults = {key: (low + high) / 2 for key, (low, high) in bounds.items()}
        defaults.update({f"s{i:02d}": 0.0 for i in range(1, entry["stores"] + 1)})
        runner = MarrmotRunner(entry["class_name"], entry["parameters"], entry["stores"])
        models[name] = Model(name, "daily", defaults, bounds, runner, f"MARRMoT v2.1.1 rev eeb7e15 {entry['class_name']}; standardized continuous structure, not original model", temperature_required=entry["temperature_required"], backend="octave")
    return models


def configure_marrmot(*, octave=None, package_list=None, timeout=300):
    """Configure picklable runners; settings survive spawned basin workers."""
    from .models import get_model, MODELS
    if not np.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite.")
    get_model("GR4J")
    from . import models as registry_module
    changed = []
    for name, model in list(registry_module.MODELS.items()):
        if isinstance(model.runner, MarrmotRunner):
            runner = replace(model.runner, executable=str(octave) if octave else None, package_list=str(package_list) if package_list else None, timeout=float(timeout))
            registry_module.MODELS[name] = replace(model, runner=runner)
            changed.append(name)
    return changed


def check_marrmot(*, octave=None, package_list=None, timeout=30):
    """Start the runtime and instantiate every class, checking optim too."""
    session = _session(str(octave) if octave else None, str(package_list) if package_list else None, timeout)
    with session.lock:
        description = session.request({"op": "describe"})
    if len(description["models"]) != 47:
        raise EngineUnavailableError("Expected all 47 MARRMoT structures.")
    return description


def marrmot_details(basin, model, parameters=None):
    """Expose actual ET, stores and solver residuals for diagnostics."""
    from .models import get_model
    model = get_model(model)
    if not isinstance(model.runner, MarrmotRunner):
        raise ValueError("marrmot_details requires a MARRMOT_XX model.")
    model.validate_basin(basin)
    params = model.parameters(parameters)
    result = model.runner.details(basin, params)
    q = result["qsim_mm"]
    if q.shape != basin.precipitation.shape or not np.all(np.isfinite(q)) or np.any(q < -1e-8):
        raise RuntimeError("MARRMoT produced invalid streamflow.")
    return result
