import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from underpass_tools.carving import carve_file


def corpus(path):
    root = {
        "type": "CityJSON",
        "version": "2.0",
        "transform": {"scale": [0.001] * 3, "translate": [0, 0, 0]},
        "metadata": {"geographicalExtent": [0, 0, 0, 20, 10, 6]},
        "CityObjects": {},
        "vertices": [],
    }
    vertices = [
        [0, 0, 0],
        [10000, 0, 0],
        [10000, 10000, 0],
        [0, 10000, 0],
        [0, 0, 6000],
        [10000, 0, 6000],
        [10000, 10000, 6000],
        [0, 10000, 6000],
    ]
    solid = {
        "type": "Solid",
        "lod": "2.2",
        "boundaries": [
            [
                [[0, 3, 2, 1]],
                [[4, 5, 6, 7]],
                [[0, 1, 5, 4]],
                [[1, 2, 6, 5]],
                [[2, 3, 7, 6]],
                [[3, 0, 4, 7]],
            ]
        ],
    }
    low = deepcopy(solid)
    low["lod"] = "1.2"
    low13 = deepcopy(low)
    low13["lod"] = "1.3"
    feature = {
        "type": "CityJSONFeature",
        "id": "B",
        "vertices": vertices,
        "CityObjects": {
            "B": {
                "type": "Building",
                "children": ["arbitrary-A", "B-7"],
                "attributes": {"keep": 5},
            },
            "arbitrary-A": {
                "type": "BuildingPart",
                "parents": ["B"],
                "geometry": [deepcopy(low), deepcopy(low13), deepcopy(solid)],
            },
            "B-7": {
                "type": "BuildingPart",
                "parents": ["B"],
                "geometry": [deepcopy(solid)],
            },
        },
    }
    path.write_text(json.dumps(root) + "\n" + json.dumps(feature) + "\n")
    return root, feature


def test_all_parts_single_invocation_and_preserved_tree(tmp_path, monkeypatch):
    source, output = tmp_path / "input.city.jsonl", tmp_path / "output.city.jsonl"
    root, original = corpus(source)
    calls = []

    def native(command, **kwargs):
        calls.append(command)
        header, *parts = [
            json.loads(line) for line in Path(command[2]).read_text().splitlines()
        ]
        assert len(parts) == 2
        for part in parts:
            target = part["CityObjects"]["B-0"]
            target.setdefault("attributes", {})["add_underpass_success"] = 1
            target["geometry"][0]["semantics"] = {
                "surfaces": [
                    {"type": "OuterCeilingSurface", "underpass_source": "heuristic"}
                ],
                "values": [[0] * 6],
            }
        Path(command[3]).write_text(
            "\n".join(json.dumps(p) for p in [header, *parts]) + "\n"
        )

    monkeypatch.setattr(subprocess, "run", native)
    report = carve_file(source, output, "test.gpkg", executable="kernel")
    result = [json.loads(line) for line in output.read_text().splitlines()][1]
    assert len(calls) == 1
    assert report["modified"] == 2
    assert result["CityObjects"]["B"] == original["CityObjects"]["B"]
    assert (
        result["CityObjects"]["arbitrary-A"]["geometry"][0]
        == original["CityObjects"]["arbitrary-A"]["geometry"][0]
    )
    assert result["CityObjects"].keys() == original["CityObjects"].keys()
    for part in ("arbitrary-A", "B-7"):
        assert (
            result["CityObjects"][part]["geometry"][-1]["semantics"]["surfaces"][0][
                "type"
            ]
            == "OuterCeilingSurface"
        )


def test_no_match_and_native_failure(tmp_path, monkeypatch):
    source = tmp_path / "input.city.jsonl"
    corpus(source)
    output = tmp_path / "output.city.jsonl"

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(subprocess, "run", fail)
    assert carve_file(source, output, "test.gpkg", building_ids=set())["features"] == 1
    before = output.read_bytes()
    with pytest.raises(subprocess.CalledProcessError):
        carve_file(source, output, "test.gpkg", executable="kernel")
    assert output.read_bytes() == before


@pytest.mark.skipif(
    not os.getenv("EXE_PATH_ADD_UNDERPASS_NATIVE"),
    reason="Native kernel not configured",
)
def test_real_native_carves_both_parts_and_preserves_other_lods(tmp_path):
    import sqlite3
    import struct

    from pyproj import CRS
    from shapely.geometry import box

    source = tmp_path / "input.city.jsonl"
    _, original = corpus(source)
    polygons = tmp_path / "underpasses.gpkg"
    with sqlite3.connect(polygons) as db:
        db.execute("PRAGMA application_id=1196444487")
        db.execute("PRAGMA user_version=10300")
        db.execute(
            "CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL,srs_id INTEGER PRIMARY KEY,organization TEXT NOT NULL,organization_coordsys_id INTEGER NOT NULL,definition TEXT NOT NULL,description TEXT)"
        )
        db.execute(
            "INSERT INTO gpkg_spatial_ref_sys VALUES ('RD New',28992,'EPSG',28992,?,'RD New')",
            (CRS.from_epsg(28992).to_wkt(),),
        )
        db.execute(
            "CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY,data_type TEXT NOT NULL,identifier TEXT,description TEXT,last_change DATETIME DEFAULT '2026-01-01T00:00:00.000Z',min_x DOUBLE,min_y DOUBLE,max_x DOUBLE,max_y DOUBLE,srs_id INTEGER)"
        )
        db.execute(
            "INSERT INTO gpkg_contents (table_name,data_type,identifier,srs_id) VALUES ('underpasses','features','underpasses',28992)"
        )
        db.execute(
            "CREATE TABLE gpkg_geometry_columns (table_name TEXT,column_name TEXT,geometry_type_name TEXT,srs_id INTEGER,z INTEGER,m INTEGER)"
        )
        db.execute(
            "INSERT INTO gpkg_geometry_columns VALUES ('underpasses','geom','POLYGON',28992,0,0)"
        )
        db.execute(
            "CREATE TABLE underpasses (fid INTEGER PRIMARY KEY,identificatie TEXT,underpass_candidate_elevations REAL,underpass_source TEXT,geom BLOB)"
        )
        geometry = (
            b"GP" + bytes([0, 1]) + struct.pack("<i", 28992) + box(3, -1, 7, 5).wkb
        )
        db.execute(
            "INSERT INTO underpasses VALUES (1,'B',NULL,'heuristic',?)", (geometry,)
        )
    output = tmp_path / "output.city.jsonl"
    report = carve_file(source, output, str(polygons), log_path=tmp_path / "native.log")
    assert report["modified"] == 2, (tmp_path / "native.log").read_text()
    result = json.loads(output.read_text().splitlines()[1])
    assert result["CityObjects"]["B"] == original["CityObjects"]["B"]
    assert (
        result["CityObjects"]["arbitrary-A"]["geometry"][0]
        == original["CityObjects"]["arbitrary-A"]["geometry"][0]
    )
    assert (
        result["CityObjects"]["arbitrary-A"]["geometry"][:2]
        == original["CityObjects"]["arbitrary-A"]["geometry"][:2]
    )
    for part in ("arbitrary-A", "B-7"):
        surfaces = result["CityObjects"][part]["geometry"][-1]["semantics"]["surfaces"]
        ceilings = [s for s in surfaces if s["type"] == "OuterCeilingSurface"]
        assert ceilings and all(s["underpass_source"] == "heuristic" for s in ceilings)
