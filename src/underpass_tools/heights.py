"""Portable, bounded street-lidar batch API; callers own persistence."""

import math
import multiprocessing
import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from .lidar import HeightResult as HeightResult
from .lidar import UnderpassRecord as UnderpassRecord
from .lidar import load_tile_index, null_result, process_batch, spatial_batches
from .terrain import terrain_sampler


@dataclass(frozen=True)
class HeightSettings:
    index: str | None = None
    pointcloud_root: str | None = None
    index_layer: str | None = None
    batch_workers: int = 16
    pip_workers: int = 5
    height_workers: int = 1
    rayon_threads: int = 3
    grid_cell_size: float = 500
    batch_size: int = 200
    chunk_size: int = 1_000_000
    min_points: int = 1000
    max_points_per_underpass: int = 10_000_000
    polygon_buffer: float = -0.2
    terrain_percentile: float = 90
    terrain_peak_exclusion_distance: float = 2
    resolution: int = 64
    laz_backend: str = "lazrs-parallel"
    decompression: str = "xyz"

    def __post_init__(self):
        for key in (
            "batch_workers",
            "pip_workers",
            "height_workers",
            "rayon_threads",
            "batch_size",
            "chunk_size",
            "max_points_per_underpass",
            "resolution",
        ):
            if getattr(self, key) < 1:
                raise ValueError(f"{key} must be positive")
        if not math.isfinite(self.grid_cell_size) or self.grid_cell_size <= 0:
            raise ValueError("grid_cell_size must be positive and finite")
        if self.min_points < 0 or not math.isfinite(self.polygon_buffer):
            raise ValueError("Invalid point threshold or polygon buffer")
        if (
            not math.isfinite(self.terrain_percentile)
            or not 0 <= self.terrain_percentile <= 100
        ):
            raise ValueError("Invalid terrain percentile")
        if (
            not math.isfinite(self.terrain_peak_exclusion_distance)
            or self.terrain_peak_exclusion_distance < 0
        ):
            raise ValueError("Invalid terrain peak exclusion distance")
        if bool(self.index) != bool(self.pointcloud_root):
            raise ValueError("Configure both the lidar index and pointcloud root")


_index = None
_args = None


def _init_worker(settings, rasters):
    global _index, _args
    os.environ["RAYON_NUM_THREADS"] = str(settings.rayon_threads)
    _index = load_tile_index(
        Path(settings.index), Path(settings.pointcloud_root), settings.index_layer
    )
    _args = SimpleNamespace(
        **settings.__dict__,
        terrain_rasters=rasters,
        terrain=True,
        crop_output_dir=None,
        reuse_cropped=False,
        write_cropped=False,
        plot_dir=None,
        plot_rerun=False,
    )
    terrain_sampler(rasters)


def _process(batch):
    return process_batch(batch.records, _index, _args)[0]


def estimate_heights(records, rasters, settings=HeightSettings()):
    """Yield batches of results, including rows outside lidar/terrain coverage.

    Lidar XYZ and terrain elevations must both use NAP. Input failures raise;
    expected per-polygon sampling failures return explicit nullable results.
    """
    rasters = tuple(map(str, rasters))
    terrain_sampler(rasters)  # Fail before creating workers for corrupt inputs.
    if settings.index is None:
        for start in range(0, len(records), settings.batch_size):
            yield [
                null_result(r, "no_laz_tiles", 0, 0, "No street lidar configured")
                for r in records[start : start + settings.batch_size]
            ]
        return
    if (
        not Path(settings.index).is_file()
        or not Path(settings.pointcloud_root).is_dir()
    ):
        raise FileNotFoundError("Configured street-lidar index/root is missing")
    # Validate in the parent so bad input doesn't look like a worker failure.
    load_tile_index(
        Path(settings.index), Path(settings.pointcloud_root), settings.index_layer
    )
    batches = iter(
        spatial_batches(records, settings.grid_cell_size, settings.batch_size)
    )
    if settings.batch_workers == 1:
        _init_worker(settings, rasters)
        for batch in batches:
            yield _process(batch)
        return
    with ProcessPoolExecutor(
        max_workers=settings.batch_workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_init_worker,
        initargs=(settings, rasters),
    ) as pool:
        pending = set()
        exhausted = False
        while pending or not exhausted:
            while not exhausted and len(pending) < settings.batch_workers * 2:
                try:
                    pending.add(pool.submit(_process, next(batches)))
                except StopIteration:
                    exhausted = True
            if pending:
                ready, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in ready:
                    yield future.result()
