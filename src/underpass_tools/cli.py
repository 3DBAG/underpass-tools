"""Standalone GeoJSON-to-JSONL street-lidar height estimation."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from shapely.geometry import shape

from .heights import HeightSettings, UnderpassRecord, estimate_heights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("polygons", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--terrain", type=Path, action="append", required=True)
    parser.add_argument("--index")
    parser.add_argument("--pointcloud-root")
    parser.add_argument("--batch-workers", type=int, default=16)
    args = parser.parse_args()
    features = json.loads(args.polygons.read_text())["features"]
    records = [
        UnderpassRecord(
            f["properties"]["identificatie"],
            f["properties"]["underpass_id"],
            shape(f["geometry"]),
        )
        for f in features
    ]
    settings = HeightSettings(
        index=args.index,
        pointcloud_root=args.pointcloud_root,
        batch_workers=args.batch_workers,
    )
    with args.output.open("w") as stream:
        for results in estimate_heights(records, args.terrain, settings):
            for result in results:
                stream.write(json.dumps(asdict(result)) + "\n")
