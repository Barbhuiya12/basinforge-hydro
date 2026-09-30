"""Generate plain study documentation with Material for MkDocs.

Model pages are derived from the actual registry. Research/results/attribution
come from the maintained Markdown sources, not hand-written demo data.
"""
import argparse
import inspect
import json
from pathlib import Path
import posixpath
import re
import shutil
import tempfile

import basinforge
from basinforge import __version__, list_models
from mkdocs.commands.build import build as mkdocs_build
from mkdocs.config import load_config

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/Barbhuiya12/basinforge-hydro"


def model_data():
    manifest = json.loads((ROOT / "src/basinforge/marrmot_manifest.json").read_text())
    structures = {"MARRMOT_" + item["class_name"].split("_")[1]: item for item in manifest}
    models = list_models(include_optional=True)
    for model in models:
        item = structures.get(model["name"])
        model["stores"] = item["stores"] if item else None
        model["temperature_required"] = item["temperature_required"] if item else model["name"] == "HBV"
        model["structure"] = item["class_name"].split("_")[2] if item else model["name"]
        if item:
            source = "_vendor/marrmot/" + item["class_name"] + ".m"
        elif model["name"] in {"GR3J", "GR5J", "GR6J", "HYMOD_CLASSIC", "XAJ", "XAJ_MZ"}:
            key = "hymod" if model["name"] == "HYMOD_CLASSIC" else "xaj" if model["name"].startswith("XAJ") else model["name"].lower()
            source = "_vendor/hydromodel/" + key + ".py"
        else:
            source = "water_balance.py" if model["name"] == "ABCD" else "extended_models.py" if model["name"] == "SMART" else "models.py"
        model["source"] = REPOSITORY + "/blob/main/src/basinforge/" + source
    return models


def reference_page(model):
    name = model["name"]
    lines = [f"# {name}", "", "## Implementation", "", model["variant"], "", f"- **Time step:** {model['timestep']}", f"- **Backend:** {model['runtime_requirement']}", f"- **Calibrated parameters:** {len(model['calibrated_parameters'])}", f"- **Temperature required:** {'yes' if model['temperature_required'] else 'no'}", "", f"[Inspect the exact implementation]({model['source']}).", "", "## Parameters and initial configuration", "", "| Parameter | Supported calibration range | Default |", "| --- | --- | ---: |"]
    for key, value in model["defaults"].items():
        bounds = model["bounds"].get(key)
        interval = f"{bounds[0]} to {bounds[1]}" if bounds else "Fixed initial/configuration value"
        lines.append(f"| `{key}` | {interval} | {value} |")
    lines += ["", "Ranges/defaults are implementation contracts, not universal priors or a recommended basin calibration. Consult source comments for parameter units and coupling.", ""]
    if model["backend"] == "octave":
        lines += ["!!! note \"MARRMoT variant\"", "    This standardized structure is not identical to the original named model. `p01...` follow exact source order; `s01...` are fixed initial stores, defaulting to zero. Octave + optim are required. Solver behavior can differ across runtime versions.", ""]
    lines += ["## Simulation", "", "```python", "from basinforge import Basin, get_model", "", f'basin = Basin.from_csv("basin.csv", basin_id="A", area_km2=1200,', f'                       q_unit="m3/s", timestep="{model["timestep"]}")', f'q_mm = get_model("{name}").simulate(basin)', "q_m3s = basin.to_m3s(q_mm)", "```", "", "Supply your actual data and catchment area; temperature-dependent models require a temperature column. For non-daily models, choose an appropriate warmup in model steps.", "", "See [calibration](../calibration.md), [input requirements](../data.md), [sources](../credits.md) and [verification limitations](../study.md).", ""]
    return "\n".join(lines)


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Refusing existing build directory: {output}")
    models = model_data()
    results = []
    for line in (ROOT / "docs/VERIFICATION.md").read_text().splitlines():
        if line.startswith("| ") and " / " in line:
            cells = [s.strip().replace("−", "-") for s in line.strip("|").split("|")]
            if len(cells) == 5:
                results.append({"model": cells[0], "training_nse": float(cells[1]), "validation_nse": float(cells[2]), "validation_kge": float(cells[3]), "seconds": float(cells[4].removesuffix(" s"))})
    if len(models) != 61 or len(results) != 5:
        raise ValueError("Unexpected registry/study count; review documentation before publishing.")
    with tempfile.TemporaryDirectory(prefix="basinforge-docs-") as temporary:
        source = Path(temporary)
        shutil.copytree(ROOT / "docs/site", source, dirs_exist_ok=True)
        pages = [("guide", "README.md"), ("research", "docs/MODEL_CATALOG.md"), ("study", "docs/VERIFICATION.md"), ("credits", "THIRD_PARTY.md"), ("roadmap", "docs/ROADMAP.md")]
        routes = {original: slug + ".md" for slug, original in pages}
        routes["LICENSE"] = REPOSITORY + "/blob/main/LICENSE"
        for slug, original in pages:
            text = (ROOT / original).read_text()
            def route(match):
                target = match.group(1)
                if target.startswith(("https:", "http:", "#", "mailto:")):
                    return match.group(0)
                resolved = posixpath.normpath((Path(original).parent / target).as_posix())
                return "](" + routes.get(resolved, REPOSITORY + "/blob/main/" + resolved) + ")"
            text = re.sub(r'\]\(([^)]+)\)', route, text)
            (source / (slug + ".md")).write_text(text)
        model_dir = source / "models"
        model_dir.mkdir()
        table = ["# Models", "", "14 Python implementations and 47 optional MARRMoT structures. Click a model for its parameter bounds, defaults, forcing frequency and implementation source.", "", "MARRMoT structures are not identical to the original named models. This is not an exhaustive inventory of all published lumped models.", "", "| Model | Structure | Time step | Backend | Parameters |", "| --- | --- | --- | --- | ---: |"]
        python_nav, octave_nav = [], []
        for model in models:
            name = model["name"]
            (model_dir / (name + ".md")).write_text(reference_page(model))
            table.append(f"| [{name}]({name}.md) | {model['structure']} | {model['timestep']} | {model['backend']} | {len(model['calibrated_parameters'])} |")
            (octave_nav if model["backend"] == "octave" else python_nav).append({name: "models/" + name + ".md"})
        (model_dir / "index.md").write_text("\n".join(table))
        api = ["# API reference", "", "Signatures below are generated from the installed package. See the guides for complete workflows and required units.", ""]
        for name in ["Basin", "Model", "CalibrationConfig", "calibrate", "calibrate_many", "calibrate_shared", "compare_models", "calibrate_multistart", "simulate_ensemble", "export_report", "get_model", "list_models", "configure_marrmot", "check_marrmot", "marrmot_details", "close_marrmot"]:
            obj = getattr(basinforge, name)
            api += ["## " + name, "", "```python", name + str(inspect.signature(obj)), "```", ""]
        (source / "api.md").write_text("\n".join(api))
        nav = [{"Home": "index.md"}, {"Installation": "installation.md"}, {"Input data": "data.md"}, {"Models": [{"Overview": "models/index.md"}, {"Python models": python_nav}, {"MARRMoT structures": octave_nav}]}, {"Workflows": [{"Single-basin calibration": "calibration.md"}, {"Multi-basin calibration": "multi-basin.md"}, {"Examples & reports": "examples.md"}]}, {"Study": [{"Verification results": "study.md"}, {"Research inventory": "research.md"}, {"Roadmap": "roadmap.md"}]}, {"API reference": "api.md"}, {"Complete user guide": "guide.md"}, {"Sources & licenses": "credits.md"}]
        config = load_config(config_file=str(ROOT / "mkdocs.yml"), docs_dir=str(source), site_dir=str(output), nav=nav)
        mkdocs_build(config)
    (output / "data.json").write_text(json.dumps({"version": __version__, "models": models, "results": results}, indent=2, allow_nan=False))
    (output / ".nojekyll").touch()
    print(f"Built Material documentation: {len(models)} model pages, guides, search and study results at {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_site"))
    build(parser.parse_args().output)
