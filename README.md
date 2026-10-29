# Underpass tools

Portable tools extracted from `underpass-detection-experiments`. There is no
Dagster, database schema, HTTP terrain service, or sibling checkout dependency.
`PROVENANCE.json` identifies the imported experimental sources.

Build/install the Python package with Zig 0.15.2 on PATH (`pip install .`).
Its platform wheel includes the Zig point-in-polygon shared library.
`streetlidar-heights polygons.geojson results.jsonl --terrain filled-ahn.tif
--index lidar.gpkg --pointcloud-root /data/lidar` expects polygons and lidar in
RD New with NAP elevations. Terrain rasters must explicitly declare NAP.

Build the native kernel using `nix build ./native/carving`, or enter its Nix shell
and run `zig build -Doptimize=ReleaseFast`. Configure
`EXE_PATH_ADD_UNDERPASS_NATIVE` to the resulting executable.
`add-underpasses OGR_SOURCE input.city.jsonl output.city.jsonl --report report.json`
batches every LoD 2.2 Solid in all BuildingParts through one native process,
then merges only replacement geometries back into the original features.
`--log` captures native diagnostics. Missing/invalid lidar candidates use a 2.5 m
ceiling above the part floor; accepted candidates must be at least 2 m above it.

Terrain sampling uses P90 of native 5 m pixels (centres inside each polygon,
intersecting pixels for tiny polygons), with first-valid manifest order for
overlaps. Missing terrain produces a nullable estimate, never unfiltered peaks.
The maximum point count per polygon bounds memory independently of LAZ chunking.

The Python tools and native kernel can be installed independently. Sources for
both are retained here; the pipeline vendors version 0.1.0 until a remote release
is available. Run `pytest tests` for portable tests.
