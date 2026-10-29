import sqlite3
import struct

import laspy
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from underpass_tools.heights import HeightSettings, UnderpassRecord, estimate_heights


def inputs(tmp_path):
    terrain = tmp_path / "terrain.tif"
    with rasterio.open(
        terrain,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="float32",
        crs="EPSG:28992",
        transform=from_origin(-10, 30, 5, 5),
        nodata=-9999,
    ) as ds:
        ds.write(np.zeros((8, 8), dtype="float32"), 1)
        ds.update_tags(HEIGHT_REFERENCE="NAP")
    index = tmp_path / "lidar.gpkg"
    geometry = b"GP" + bytes([0, 1]) + struct.pack("<i", 28992) + box(0, 0, 10, 10).wkb
    with sqlite3.connect(index) as db:
        db.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)")
        db.execute("INSERT INTO gpkg_contents VALUES ('tiles','features')")
        db.execute(
            "CREATE TABLE gpkg_geometry_columns (table_name TEXT,column_name TEXT)"
        )
        db.execute("INSERT INTO gpkg_geometry_columns VALUES ('tiles','geom')")
        db.execute("CREATE TABLE tiles (location TEXT,geom BLOB)")
        db.execute("INSERT INTO tiles VALUES ('cloud.laz',?)", (geometry,))
    points = laspy.LasData(laspy.LasHeader(point_format=3, version="1.2"))
    rng = np.random.default_rng(2026)
    points.x = rng.uniform(1, 9, 4000)
    points.y = rng.uniform(1, 9, 4000)
    points.z = np.full(4000, 3.3)
    points.write(tmp_path / "cloud.laz")
    return terrain, index


@pytest.mark.parametrize("batch_workers", [1, 2])
def test_real_laz_crop_terrain_and_missing_coverage(
    tmp_path, monkeypatch, batch_workers
):
    terrain, index = inputs(tmp_path)
    # No downloader should be involved in a height run.
    import socket

    monkeypatch.setattr(
        socket.socket,
        "connect",
        lambda *args: pytest.fail("Network used during height estimation"),
    )
    records = [
        UnderpassRecord("B", 1, box(0, 0, 10, 10)),
        UnderpassRecord("C", 2, box(100, 100, 110, 110)),
    ]
    settings = HeightSettings(
        index=str(index),
        pointcloud_root=str(tmp_path),
        batch_workers=batch_workers,
        pip_workers=1,
        grid_cell_size=50,
    )
    results = {
        r.underpass_id: r
        for batch in estimate_heights(records, [terrain], settings)
        for r in batch
    }
    assert set(results) == {1, 2}
    assert results[1].status == "success"
    assert results[1].point_count == 4000
    assert results[1].terrain_elevation == 0
    assert results[1].candidate_elevation == pytest.approx(3.3, abs=0.15)
    assert results[2].status == "no_laz_tiles"


def test_missing_lidar_produces_explicit_results(tmp_path):
    terrain, _ = inputs(tmp_path)
    result = list(
        estimate_heights(
            [UnderpassRecord("B", 1, box(0, 0, 10, 10))], [terrain], HeightSettings()
        )
    )[0][0]
    assert result.status == "no_laz_tiles"
    assert result.candidate_elevation is None


def test_unavailable_terrain_never_emits_unfiltered_peak(tmp_path):
    terrain, index = inputs(tmp_path)
    with rasterio.open(terrain, "r+") as ds:
        ds.write(np.full((8, 8), -9999, dtype="float32"), 1)
    settings = HeightSettings(
        index=str(index), pointcloud_root=str(tmp_path), batch_workers=1, pip_workers=1
    )
    result = list(
        estimate_heights(
            [UnderpassRecord("B", 1, box(0, 0, 10, 10))], [terrain], settings
        )
    )[0][0]
    assert result.status == "failed" and result.candidate_elevation is None
