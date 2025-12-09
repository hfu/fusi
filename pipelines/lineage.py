#!/usr/bin/env python3
"""Lineage tile helpers: generate per-pixel source provenance visualizations.

This module provides a prototype to convert a provenance mask (source index
per pixel) into an RGB image suitable for storing as a companion "lineage"
tile. The heavy lifting (reprojection + provenance mask) is delegated to
`pipelines.aggregate_pmtiles.compute_tile_provenance`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

try:
    import mercantile
except Exception:  # pragma: no cover - optional
    mercantile = None
import numpy as np

from .aggregate_pmtiles import (
    build_records_from_sources,
    compute_tile_provenance,
    intersects,
    SourceRecord,
)


def default_palette() -> Dict[int, Tuple[int, int, int]]:
    """Return a default palette mapping source index -> RGB.
    """
    return {
        -1: (255, 255, 255),  # nodata -> white
        0: (0, 100, 0),       # dark green
        1: (50, 205, 50),     # medium green (lime green)
        2: (152, 251, 152),   # light green (pale green)
        3: (34, 139, 34),     # forest green
        4: (60, 179, 113),    # medium sea green
        5: (144, 238, 144),   # light green (lighter than #2)
        6: (193, 255, 193),   # very light green (minty; high priority number)
    }


def provenance_to_rgb(prov_mask: np.ndarray, palette: Optional[Dict[int, Tuple[int, int, int]]] = None) -> np.ndarray:
    """Map a provenance integer mask to an RGB uint8 image.

    prov_mask: 2D array of ints (e.g., -1 for nodata, 0..N for source indices)
    Returns: HxWx3 uint8 RGB image
    """
    if prov_mask is None:
        return None
    if palette is None:
        palette = default_palette()

    h, w = prov_mask.shape
    out = np.zeros((h, w, 3), dtype=np.uint8)

    unique = np.unique(prov_mask)
    for val in unique:
        color = palette.get(int(val))
        if color is None:
            # Fallback: generate a green-ish tone by index
            idx = int(val)
            g = 120 + ((idx * 37) % 120)
            color = (200 - (idx % 60), g, 100 + ((idx * 23) % 120))
        mask = prov_mask == val
        out[mask] = color

    return out


def generate_lineage_tile(
    sources: Iterable[str],
    z: int,
    x: int,
    y: int,
    out_shape: Tuple[int, int] = (512, 512),
    warp_threads: int = 1,
) -> Optional[np.ndarray]:
    """Generate an RGB lineage tile for the given sources and tile coords.

    This is a prototype convenience: it loads `bounds.csv` metadata for the
    provided sources (in order), selects overlapping records, computes the
    provenance mask, and returns an RGB array (uint8) suitable for encoding.
    """
    # Build records from sources preserving priority order
    records = build_records_from_sources(list(sources))

    # Determine mercator tile bounds
    tile = mercantile.Tile(x=x, y=y, z=z)
    tile_bounds = mercantile.xy_bounds(tile)

    # Filter overlapping records
    overlapping = [r for r in records if intersects(r.bounds_mercator, (tile_bounds.left, tile_bounds.bottom, tile_bounds.right, tile_bounds.top))]
    if not overlapping:
        return None

    merged, provenance = compute_tile_provenance(overlapping, tile_bounds, out_shape=out_shape, warp_threads=warp_threads)
    if provenance is None:
        return None

    rgb = provenance_to_rgb(provenance)
    return rgb


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate lineage tile (RGB) for given sources and tile coords")
    parser.add_argument("--z", type=int, required=True)
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y", type=int, required=True)
    parser.add_argument("--sources", nargs="+", required=True)
    parser.add_argument("--out", help="Output PNG path (optional)")
    args = parser.parse_args(argv)

    rgb = generate_lineage_tile(args.sources, args.z, args.x, args.y)
    if rgb is None:
        print("No provenance available for requested tile")
        return 1

    out = args.out
    if out:
        from PIL import Image

        img = Image.fromarray(rgb)
        img.save(out)
        print(f"Wrote lineage tile to {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
