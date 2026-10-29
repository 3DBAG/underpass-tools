# Underpass tools

Underpass tools extracted from `underpass-detection-experiments` for integration into 3dbag-pipeline. 
`PROVENANCE.json` identifies the imported experimental sources.

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
