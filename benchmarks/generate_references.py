"""Generate reference JSON using independent official source checkouts.

This is a developer tool, not a synthetic-observation demonstration. The
forcing fixture is controlled and explicitly artificial; expected simulations
are calculated by upstream code, not by the BasinForge adapters.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

import numpy as np
from scipy.io import loadmat, savemat


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hydromodel", type=Path, required=True)
    parser.add_argument("--marrmot", type=Path, required=True)
    parser.add_argument("--octave", type=Path, required=True)
    parser.add_argument("--package-list", type=Path, required=True)
    args = parser.parse_args()
    precipitation = np.resize([0., 10., 2., 20., 0.], 30)
    pet = np.full(30, 2.0)
    temperature = np.linspace(-5, 15, 30)
    # Avoid upstream hydromodel's unrelated data-layer imports. Its original
    # model modules are loaded unchanged under their original namespace.
    root = types.ModuleType("hydromodel")
    root.__path__ = [str(args.hydromodel / "hydromodel")]
    models = types.ModuleType("hydromodel.models")
    models.__path__ = [str(args.hydromodel / "hydromodel" / "models")]
    sys.modules.update({"hydromodel": root, "hydromodel.models": models})
    contract = importlib.import_module("hydromodel.models.model_config").MODEL_PARAM_DICT
    python_models = {}
    for key in ["gr3j", "gr5j", "gr6j", "hymod", "xaj", "xaj_mz"]:
        metadata = contract[key]
        bounds = dict(metadata["param_range"])
        if key.startswith("xaj"):
            bounds.update(UM=(.1, bounds["UM"][1]), KI=(.001, bounds["KI"][1]), KG=(.001, bounds["KG"][1]))
        if key == "xaj_mz":
            bounds.update(A=(.1, bounds["A"][1]), THETA=(.1, bounds["THETA"][1]))
        parameters = {name: sum(bounds[name])/2 for name in metadata["param_name"]}
        module = "xaj" if key.startswith("xaj") else key
        function = getattr(importlib.import_module("hydromodel.models." + module), module)
        output = function(np.column_stack((precipitation, pet))[:, None, :], np.array([[parameters[name] for name in metadata["param_name"]]]), warmup_length=0, normalized_params=False, param_config={key: metadata}, name=key, time_interval_hours=24)[0][:, 0, 0]
        python_models[key] = {"parameters": parameters, "qsim_mm": output.tolist()}
    quote = lambda path: "'" + str(path).replace("'", "''") + "'"
    with tempfile.TemporaryDirectory(prefix="basinforge-reference-") as temporary:
        source = Path(temporary) / "forcing.mat"
        target = Path(temporary) / "reference.mat"
        savemat(source, {"forcing": np.column_stack((precipitation, pet, temperature))})
        # One-shot upstream call. No BasinForge MATLAB wrapper or model code
        # is on the Octave search path in this independent reference run.
        expression = f"warning('off','Octave:shadowed-function'); pkg('local_list',{quote(args.package_list)}); addpath(genpath({quote(args.marrmot / 'MARRMoT')})); load({quote(source)}); files=dir(fullfile({quote(args.marrmot / 'MARRMoT' / 'Models' / 'Model files')},'m_*.m')); reference=struct(); for i=1:length(files); classname=files(i).name(1:end-2); if isempty(regexp(classname,'^m_[0-9][0-9]_.*_[0-9]+p_[0-9]+s$','once')); continue; end; rng(0,'twister'); m=feval(classname); m.delta_t=1; m.input_climate=forcing; m.theta=mean(m.parRanges,2); m.S0=zeros(m.numStores,1); m.solver_opts=[]; reference.(classname)=m.get_streamflow(); end; save('-mat7-binary',{quote(target)},'reference');"
        environment = os.environ.copy()
        environment.update(OCTAVE_HOME=str(args.octave.parent.parent), OCTAVE_EXEC_HOME=str(args.octave.parent.parent))
        subprocess.run([str(args.octave), "--norc", "--no-history", "--quiet", "--eval", expression], env=environment, check=True, capture_output=True, timeout=300)
        reference = loadmat(target, simplify_cells=True)["reference"]
        octave_models = {name: np.asarray(values).reshape(-1).tolist() for name, values in reference.items()}
    result = {"description": "controlled artificial forcing; independent upstream simulations, not observations", "hydromodel_revision": "89d7a8ed1d72ce4fffbbd9897490b089382ecbac", "marrmot_revision": "eeb7e152d4bc194a6fa9407e3d79e2e29ba7e201", "forcing": {"precipitation": precipitation.tolist(), "pet": pet.tolist(), "temperature": temperature.tolist()}, "hydromodel": python_models, "marrmot": octave_models}
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
