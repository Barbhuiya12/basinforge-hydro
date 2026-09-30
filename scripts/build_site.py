"""Build the study site from real registry/documentation; no external API."""
import argparse
import html
import json
from pathlib import Path
import re
import shutil

import markdown
from basinforge import __version__, list_models

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/Barbhuiya12/basinforge-hydro"


def build(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Refusing existing build directory: {output}")
    manifest = json.loads((ROOT / "src/basinforge/marrmot_manifest.json").read_text())
    structures = {"MARRMOT_" + item["class_name"].split("_")[1]: item for item in manifest}
    models = list_models(include_optional=True)
    for model in models:
        item = structures.get(model["name"])
        model["stores"] = item["stores"] if item else None
        model["temperature_required"] = item["temperature_required"] if item else model["name"] == "HBV"
        model["structure"] = item["class_name"].split("_")[2] if item else model["name"]
        if item:
            source_path = "src/basinforge/_vendor/marrmot/" + item["class_name"] + ".m"
        elif model["name"] in {"GR3J", "GR5J", "GR6J", "HYMOD_CLASSIC", "XAJ", "XAJ_MZ"}:
            key = "hymod" if model["name"] == "HYMOD_CLASSIC" else "xaj" if model["name"].startswith("XAJ") else model["name"].lower()
            source_path = "src/basinforge/_vendor/hydromodel/" + key + ".py"
        else:
            source_path = "src/basinforge/" + ("water_balance.py" if model["name"] == "ABCD" else "extended_models.py" if model["name"] == "SMART" else "models.py")
        model["source"] = REPOSITORY + "/blob/main/" + source_path
    study = (ROOT / "docs/VERIFICATION.md").read_text()
    results = []
    for line in study.splitlines():
        if line.startswith("| ") and " / " in line:
            cells = [s.strip().replace("−", "-") for s in line.strip("|").split("|")]
            if len(cells) == 5:
                results.append({"model": cells[0], "training_nse": float(cells[1]), "validation_nse": float(cells[2]), "validation_kge": float(cells[3]), "seconds": float(cells[4].removesuffix(" s"))})
    if len(models) != 61 or len(results) != 5:
        raise ValueError("Unexpected registry/study count; review the site content before publishing.")
    shutil.copytree(ROOT / "website", output)
    (output / "data.json").write_text(json.dumps({"version": __version__, "models": models, "results": results}, indent=2, allow_nan=False))
    template = (ROOT / "website/document.html").read_text()
    pages = [("guide", "User guide", "README.md"), ("research", "Model research catalog", "docs/MODEL_CATALOG.md"), ("study", "Verification study", "docs/VERIFICATION.md"), ("credits", "Scientific sources & licenses", "THIRD_PARTY.md"), ("roadmap", "Research roadmap", "docs/ROADMAP.md")]
    routes = {source: slug + ".html" for slug, _, source in pages}
    routes["LICENSE"] = REPOSITORY + "/blob/main/LICENSE"
    for slug, title, source in pages:
        body = markdown.markdown((ROOT / source).read_text(), extensions=["tables", "fenced_code", "toc"], output_format="html")
        def replace_link(match):
            target = match.group(1)
            if target.startswith(("https:", "http:", "#", "mailto:")):
                return match.group(0)
            resolved = (Path(source).parent / target).as_posix()
            # Normalize ../ attribution links without using filesystem reads.
            import posixpath
            resolved = posixpath.normpath(resolved)
            return 'href="' + html.escape(routes.get(resolved, REPOSITORY + "/blob/main/" + resolved), quote=True) + '"'
        body = re.sub(r'href="([^"]+)"', replace_link, body)
        page = template.replace("{{TITLE}}", html.escape(title)).replace("{{BODY}}", body)
        (output / (slug + ".html")).write_text(page)
    (output / "document.html").unlink()
    (output / ".nojekyll").touch()
    print(f"Built {output}: {len(models)} model entries, {len(results)} measured results, 5 study/guide pages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_site"))
    build(parser.parse_args().output)
