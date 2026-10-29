"""Multipart CityJSONSeq adapter for the native boolean kernel.

All eligible solids are batched into one native invocation per source file.
Only replacement geometries are merged back into the original feature tree.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path


def _remap(value, offset):
    if isinstance(value, list):
        return [_remap(item, offset) for item in value]
    if not isinstance(value, int) or value < 0:
        raise ValueError("Invalid CityJSON boundary index")
    return value + offset


def _read(path):
    with Path(path).open() as stream:
        items = [json.loads(line) for line in stream if line.strip()]
    if not items or items[0].get("type") != "CityJSON":
        raise ValueError(f"Expected a CityJSONSeq header: {path}")
    return items[0], items[1:]


def _write(path, root, features):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            for item in [root, *features]:
                stream.write(json.dumps(item, separators=(",", ":")) + "\n")
            stream.close()
            temporary.chmod(0o644)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def carve_file(
    source,
    destination,
    ogr_source,
    *,
    executable=None,
    building_ids=None,
    env=None,
    log_path=None,
    report_path=None,
):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Carving output must differ from the input")
    root, features = _read(source)
    if any(f.get("type") != "CityJSONFeature" for f in features):
        raise ValueError("Expected CityJSONFeature records")
    expanded, targets, report = [], [], []
    for fi, feature in enumerate(features):
        building = feature["id"]
        if building_ids is not None and building not in building_ids:
            continue
        for part_id, part in feature["CityObjects"].items():
            if part.get("type") not in ("BuildingPart", "Building"):
                continue
            for gi, geometry in enumerate(part.get("geometry", [])):
                if str(geometry.get("lod")) != "2.2":
                    continue
                if geometry.get("type") != "Solid":
                    report.append(
                        {
                            "building": building,
                            "part": part_id,
                            "geometry": gi,
                            "status": "skipped",
                            "reason": "unsupported_geometry",
                        }
                    )
                    continue
                parent = deepcopy(
                    feature["CityObjects"].get(building, {"type": "Building"})
                )
                parent["geometry"] = []
                parent["children"] = [building + "-0"]
                isolated = deepcopy(part)
                isolated.update(
                    type="BuildingPart",
                    parents=[building],
                    geometry=[deepcopy(geometry)],
                )
                isolated.pop("children", None)
                expanded.append(
                    {
                        "type": "CityJSONFeature",
                        "id": building,
                        "CityObjects": {building: parent, building + "-0": isolated},
                        "vertices": feature["vertices"],
                    }
                )
                targets.append((fi, part_id, gi))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if expanded:
        executable = (
            executable
            or os.getenv("EXE_PATH_ADD_UNDERPASS_NATIVE")
            or shutil.which("add_underpass_native")
        )
        if not executable:
            raise FileNotFoundError(
                "Configure EXE_PATH_ADD_UNDERPASS_NATIVE or install add_underpass_native"
            )
        with tempfile.TemporaryDirectory(
            prefix="underpass-carve-", dir=destination.parent
        ) as work:
            input_path, output_path = (
                Path(work) / "input.city.jsonl",
                Path(work) / "output.city.jsonl",
            )
            _write(input_path, root, expanded)
            command = [
                str(executable),
                ogr_source,
                str(input_path),
                str(output_path),
                "underpass_candidate_elevations",
                "identificatie",
                "manifold",
                "surface",
            ]
            if log_path:
                Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(log_path or os.devnull, "w") as log:
                subprocess.run(
                    command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True
                )
            output_root, processed = _read(output_path)
            if output_root.get("transform") != root.get("transform"):
                raise ValueError("Native kernel changed the CityJSONSeq transform")
            if len(processed) != len(targets):
                raise ValueError("Native kernel lost or added feature records")
            for (fi, part_id, gi), result in zip(targets, processed, strict=True):
                original = features[fi]
                if result.get("id") != original["id"]:
                    raise ValueError("Native kernel reordered feature records")
                succeeded = any(
                    obj.get("attributes", {}).get("add_underpass_success") == 1
                    for obj in result["CityObjects"].values()
                )
                status = {
                    "building": original["id"],
                    "part": part_id,
                    "geometry": gi,
                    "status": "modified" if succeeded else "unchanged",
                }
                if succeeded:
                    replacement = deepcopy(
                        result["CityObjects"][original["id"] + "-0"]["geometry"][0]
                    )
                    replacement["boundaries"] = _remap(
                        replacement["boundaries"], len(original["vertices"])
                    )
                    original["vertices"].extend(result["vertices"])
                    original["CityObjects"][part_id]["geometry"][gi] = replacement
                else:
                    status["reason"] = "no_applicable_cut_or_geometry_failure"
                report.append(status)
    _write(destination, root, features)
    summary = {
        "features": len(features),
        "parts": report,
        **{
            key: sum(r["status"] == key for r in report)
            for key in ("modified", "unchanged", "skipped")
        },
    }
    if report_path:
        Path(report_path).write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ogr_source")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--native-executable")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    carve_file(
        args.input,
        args.output,
        args.ogr_source,
        executable=args.native_executable,
        log_path=args.log,
        report_path=args.report,
    )


if __name__ == "__main__":
    main()
