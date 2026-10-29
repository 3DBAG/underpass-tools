"""Windowed polygon sampling of local, filled AHN rasters in RD/NAP."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds
from shapely.geometry import box, mapping
from shapely.strtree import STRtree


class TerrainUnavailable(ValueError):
    """The polygon has no valid terrain samples."""


@dataclass(frozen=True)
class TerrainSample:
    elevation_m_nap: float
    pixel_count: int
    paths: tuple[str, ...]
    selection: str
    percentile: float

    def metadata(self):
        return {
            "source": "ahn_filled",
            "vertical_datum": "NAP",
            "vertical_crs": "EPSG:5709",
            "effective_resolution_m": 5,
            "elevation_m_nap": self.elevation_m_nap,
            "percentile": self.percentile,
            "pixel_count": self.pixel_count,
            "pixel_selection": self.selection,
            "rasters": list(self.paths),
        }


class TerrainSampler:
    def __init__(self, paths):
        self.sources = []
        for path in paths:
            with rasterio.open(path) as ds:
                if (
                    ds.crs.to_epsg() not in (28992, 7415)
                    or ds.tags().get("HEIGHT_REFERENCE", "").upper() != "NAP"
                ):
                    raise ValueError(f"Expected an RD/NAP terrain raster: {path}")
                if not np.allclose(ds.res, (5, 5)) or ds.transform.b or ds.transform.d:
                    raise ValueError(f"Expected a north-up 5 m terrain raster: {path}")
                self.sources.append((str(Path(path).resolve()), box(*ds.bounds)))
        if not self.sources:
            raise ValueError("Terrain raster collection is empty")
        self.tree = STRtree([bounds for _, bounds in self.sources])

    def sample(self, polygon, percentile=90.0):
        if polygon.is_empty or not polygon.is_valid:
            raise TerrainUnavailable("Invalid or empty terrain sampling polygon")
        if not np.isfinite(percentile) or not 0 <= percentile <= 100:
            raise ValueError("Terrain percentile must be finite and between 0 and 100")
        candidates = [
            self.sources[int(i)]
            for i in sorted(self.tree.query(polygon, predicate="intersects"))
        ]
        for all_touched in (False, True):
            values, used = {}, []
            for path, _ in candidates:
                with rasterio.open(path) as ds:
                    raw = from_bounds(*polygon.bounds, transform=ds.transform)
                    left, top = (
                        max(0, int(np.floor(raw.col_off))),
                        max(0, int(np.floor(raw.row_off))),
                    )
                    right = min(ds.width, int(np.ceil(raw.col_off + raw.width)))
                    bottom = min(ds.height, int(np.ceil(raw.row_off + raw.height)))
                    if right <= left or bottom <= top:
                        continue
                    window = Window(left, top, right - left, bottom - top)
                    data = ds.read(1, window=window, masked=True)
                    transform = ds.window_transform(window)
                    mask = geometry_mask(
                        [mapping(polygon)],
                        data.shape,
                        transform,
                        all_touched=all_touched,
                        invert=True,
                    )
                    valid = mask & ~np.ma.getmaskarray(data) & np.isfinite(data.data)
                    rows, cols = np.where(valid)
                    if rows.size:
                        used.append(path)
                    for row, col in zip(rows, cols, strict=True):
                        # Manifest order defines priority in overlapping source cells.
                        centre = transform * (float(col) + 0.5, float(row) + 0.5)
                        values.setdefault(centre, float(data.data[row, col]))
            if values:
                return TerrainSample(
                    float(np.percentile(list(values.values()), percentile)),
                    len(values),
                    tuple(used),
                    "all_touched_fallback" if all_touched else "pixel_centers",
                    percentile,
                )
        raise TerrainUnavailable("No valid filled AHN samples intersect the polygon")


@lru_cache(maxsize=2)
def terrain_sampler(paths: tuple[str, ...]) -> TerrainSampler:
    return TerrainSampler(paths)
