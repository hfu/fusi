import sys
from pathlib import Path
import numpy as np

# Ensure repo root on sys.path when tests run
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.lineage import provenance_to_rgb, default_palette


def test_provenance_to_rgb_simple():
    mask = np.array([[0, 1], [-1, 0]], dtype=int)
    pal = default_palette()
    rgb = provenance_to_rgb(mask, palette=pal)
    assert rgb.shape == (2, 2, 3)
    assert (rgb[0, 0] == np.array(pal[0])).all()
    assert (rgb[0, 1] == np.array(pal[1])).all()
    assert (rgb[1, 0] == np.array(pal[-1])).all()
