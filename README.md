# Underpass tools

Underpass tools extracted from `underpass-detection-experiments` for integration into 3dbag-pipeline. 
`PROVENANCE.json` identifies the imported experimental sources.

## Prebuilt wheels

The `Build wheels` GitHub Actions workflow builds a Linux x86_64 wheel on pull
requests, pushes to `main`, version tags, and manual runs. Wheels are built in a
manylinux 2.28 container with Zig 0.17.1, then tested against the installed package.
The native library uses a C ABI, so the same wheel works with Python 3.12 and
newer; the workflow also checks installation on Python 3.12 and 3.13 without Zig.

Download the wheel from the run's `wheels-linux-x86_64` artifact or from a
[GitHub release](https://github.com/3DBAG/underpass-tools/releases). On compatible
Linux x86_64 systems with glibc 2.28 or newer, install the downloaded wheel with:

```bash
python -m pip install ./underpass_tools-*.whl
```

To publish, set the version in `pyproject.toml` and `src/underpass_tools/__init__.py`,
then push a matching `v<version>` tag. After successful wheel tests, the workflow
creates a GitHub release (or uses an existing one) and attaches the wheel and
`SHA256SUMS`. Existing release assets are never overwritten. This publishes to
GitHub Releases, not PyPI; it uses the workflow's built-in GitHub token.

The pipeline can switch from its Git source dependency to a release wheel once
the first release is available, removing its need to install Zig.

## Building from source

With Python 3.12+ in a virtual environment and Zig 0.17.1 on PATH, build
from the package root:

```bash
python -m pip install build
python -m build
```

This writes a source archive and platform wheel to `dist/`. The wheel build
compiles and bundles the Zig point-in-polygon shared library. To build and install
locally instead, run `python -m pip install .`.

`streetlidar-heights polygons.geojson results.jsonl --terrain filled-ahn.tif
--index lidar.gpkg --pointcloud-root /data/lidar` expects polygons and lidar in
RD New with NAP elevations. Terrain rasters must explicitly declare NAP.

Terrain sampling uses P90 of native 5 m pixels (centres inside each polygon,
intersecting pixels for tiny polygons), with first-valid manifest order for
overlaps. Missing terrain produces a nullable estimate, never unfiltered peaks.
The maximum point count per polygon bounds memory independently of LAZ chunking.

Roofer performs underpass carving during building reconstruction. This package
currently provides streetlidar estimates only, including nullable results when measurements are
unavailable. Run `pytest tests` for portable tests.
