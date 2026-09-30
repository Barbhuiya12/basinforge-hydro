"""Check study exports are sourced, linkable and non-destructive."""
import importlib.util
import json
from pathlib import Path
from html.parser import HTMLParser

import pytest


def test_site_registry_results_links_and_no_overwrite(tmp_path):
    pytest.importorskip("mkdocs", reason="Install .[docs] for site-builder tests")
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("build_site", root / "scripts/build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    destination = tmp_path / "site"
    module.build(destination)
    data = json.loads((destination / "data.json").read_text())
    assert len(data["models"]) == 61
    assert sum(model["backend"] == "octave" for model in data["models"]) == 47
    assert len(data["results"]) == 5
    assert data["results"][1]["validation_nse"] < 0  # poor result is not hidden
    assert len(list((destination / "models").glob("*.html"))) == 62
    assert (destination / "search/search_index.json").exists()
    class Links(HTMLParser):
        def handle_starttag(self, tag, attributes):
            for key, value in attributes:
                if key in {"href", "src"} and value and not value.startswith(("https:", "http:", "#", "mailto:")):
                    target = value.split("#")[0].split("?")[0]
                    if target.startswith("/basinforge-hydro/"):
                        resolved = destination / target.removeprefix("/basinforge-hydro/")
                    else:
                        resolved = self.directory / target
                    assert resolved.exists(), f"Missing local link {value}"
    for page in destination.rglob("*.html"):
        parser = Links()
        parser.directory = page.parent
        parser.feed(page.read_text())
    with pytest.raises(FileExistsError, match="Refusing"):
        module.build(destination)
