import math
import sys
from pathlib import Path

import numpy as np

# Ensure repo root is on sys.path when pytest runs this file directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.aggregate_pmtiles import (
    recommended_max_zoom,
    merge_tile_candidates,
    compute_max_zoom_for_records,
    SourceRecord,
)
from pathlib import Path


def test_recommended_max_zoom_basic():
    # Very coarse resolution -> low zoom
    z = recommended_max_zoom(10000.0)
    assert isinstance(z, int)
    assert 0 <= z <= 17

    # Extremely fine resolution -> near max
    z2 = recommended_max_zoom(0.5)
    assert z2 >= z


def test_merge_tile_candidates_simple():
    a = np.array([[1.0, math.nan], [math.nan, 4.0]], dtype=np.float32)
    b = np.array([[math.nan, 2.0], [3.0, math.nan]], dtype=np.float32)
    merged = merge_tile_candidates([a, b])
    assert merged.shape == a.shape
    assert merged[0, 0] == 1.0
    assert merged[0, 1] == 2.0
    assert merged[1, 0] == 3.0
    assert merged[1, 1] == 4.0


def test_compute_max_zoom_for_records():
    # Create fake records with pixel_size values
    records = [
        SourceRecord(path=Path("/tmp/a.tif"), left=0, bottom=0, right=1, top=1, width=1000, height=1000, pixel_size=0.1, source="a", priority=0),
        SourceRecord(path=Path("/tmp/b.tif"), left=0, bottom=0, right=1, top=1, width=500, height=500, pixel_size=0.2, source="b", priority=1),
    ]
    auto = compute_max_zoom_for_records(records, user_max_zoom=None)
    assert isinstance(auto, int)
    # If user specifies, respect it
    assert compute_max_zoom_for_records(records, user_max_zoom=5) == 5


def test_merge_with_provenance():
    # Prepare two source arrays with simple fill pattern
    a = np.array([[1.0, np.nan], [np.nan, 4.0]], dtype=np.float32)
    b = np.array([[np.nan, 2.0], [3.0, np.nan]], dtype=np.float32)
    # source 0 is a, source 1 is b
    merged, prov = __import__('pipelines.aggregate_pmtiles', fromlist=['']).merge_tile_candidates_with_provenance([(0, a), (1, b)])
    assert merged[0, 0] == 1.0
    assert merged[0, 1] == 2.0
    assert merged[1, 0] == 3.0
    assert merged[1, 1] == 4.0
    # provenance: positions correspond to source indices
    assert prov[0, 0] == 0
    assert prov[0, 1] == 1
    assert prov[1, 0] == 1
    assert prov[1, 1] == 0
