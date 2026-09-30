# Installation

## Python package

Python 3.11 or later is required. Install from the source repository:

```bash
git clone https://github.com/Barbhuiya12/basinforge-hydro.git
cd basinforge-hydro
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
basinforge doctor
basinforge models
```

On Windows, replace activation with `.venv\Scripts\activate`. BasinForge has not been published to PyPI; `pip install basinforge-hydro` is not currently the supported installation method.

The Python install supplies the 14 Python model implementations. First calls to Numba-backed kernels may be slower while compiling.

## Optional MARRMoT engine

The 47 MARRMoT adapters additionally require **Octave and its optim package**. The wheel contains model source, not an Octave executable.

On Ubuntu/Debian:

```bash
sudo apt install octave octave-optim
basinforge doctor --check-marrmot
basinforge models --all
```

For other systems, use your Octave distribution and install optim using its package manager. Building packages may require a compiler and additional dependencies. With a nonstandard installation:

```bash
basinforge doctor --check-marrmot \
  --octave /path/to/octave-cli \
  --octave-package-list /path/to/local-package-list
```

The package-list argument is optional. Equivalent environment variables are `BASINFORGE_OCTAVE` and `BASINFORGE_OCTAVE_PACKAGE_LIST`.

```python
from basinforge import configure_marrmot
configure_marrmot(octave="/path/to/octave-cli", timeout=300)
```

Preflight checks constructors/dependencies. It does not establish hydrological validity for your data.

## Development and tests

```bash
python -m pip install -e '.[dev,docs]'
python -m pytest -q
python -m build
```

The default test run skips external-engine integration tests. With Octave installed:

```bash
BASINFORGE_TEST_MARRMOT=1 python -m pytest -q
```

## Build this documentation

```bash
python -m pip install -e '.[docs]'
python scripts/build_site.py --output _site
python -m http.server 8000 --directory _site
```

Open `http://localhost:8000`. Existing build directories are refused; choose another `--output` for a later build. GitHub Pages builds the same documentation automatically from `main`.
