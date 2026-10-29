import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from underpass_tools.terrain import TerrainSampler, TerrainUnavailable


def raster(path, values, *, x=0, reference="NAP"):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:28992",
        transform=from_origin(x, 20, 5, 5),
        nodata=-9999,
    ) as ds:
        ds.write(values.astype("float32"), 1)
        ds.update_tags(HEIGHT_REFERENCE=reference)
    return path


def test_p90_negative_nap_and_no_double_counting(tmp_path):
    first = raster(tmp_path / "a.tif", np.arange(-16, 0).reshape(4, 4))
    overlap = raster(tmp_path / "b.tif", np.full((4, 4), 100))
    result = TerrainSampler([first, overlap]).sample(box(0, 0, 20, 20))
    assert result.elevation_m_nap == pytest.approx(-2.5)
    assert result.pixel_count == 16
    assert result.metadata()["vertical_datum"] == "NAP"


def test_tiny_polygon_and_boundary(tmp_path):
    first = raster(tmp_path / "a.tif", np.full((4, 4), 1))
    second = raster(tmp_path / "b.tif", np.full((4, 4), 3), x=20)
    sampler = TerrainSampler([first, second])
    assert sampler.sample(box(1, 1, 2, 2)).selection == "all_touched_fallback"
    sample = sampler.sample(box(17, 1, 23, 5))
    assert sample.pixel_count == 2
    assert sample.elevation_m_nap == pytest.approx(2.8)


def test_nodata_and_wrong_reference(tmp_path):
    path = raster(tmp_path / "empty.tif", np.full((4, 4), -9999))
    with pytest.raises(TerrainUnavailable):
        TerrainSampler([path]).sample(box(0, 0, 20, 20))
    wrong = raster(tmp_path / "ellipsoid.tif", np.ones((4, 4)), reference="ellipsoidal")
    with pytest.raises(ValueError, match="RD/NAP"):
        TerrainSampler([wrong])
