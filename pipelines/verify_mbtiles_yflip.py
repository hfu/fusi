#!/usr/bin/env python3
"""Verify MBTiles tile row flip (TMS) correctness by comparing MBTiles entries
with tiles generated directly by the aggregation generator.

Usage:
    python pipelines/verify_mbtiles_yflip.py <source> <mbtiles_path> --bbox W S E N --max-zoom Z
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Dict, Tuple

try:
    import mercantile  # optional
except Exception:  # pragma: no cover - optional
    mercantile = None

from aggregate_pmtiles import load_bounds, generate_aggregated_tiles


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('source')
    p.add_argument('mbtiles')
    p.add_argument('--bbox', nargs=4, type=float, required=True)
    p.add_argument('--min-zoom', type=int, default=0)
    p.add_argument('--max-zoom', type=int, default=8)
    return p.parse_args()


def read_mbtiles_tiles(mbtiles_path: Path) -> Dict[Tuple[int,int,int], bytes]:
    conn = sqlite3.connect(str(mbtiles_path))
    cur = conn.cursor()
    cur.execute('SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles')
    out = {}
    for z, x, tile_row, data in cur:
        # MBTiles stores TMS tile_row; convert back to XYZ y
        y = (1 << z) - 1 - tile_row
        out[(z, x, y)] = data
    conn.close()
    return out


def main():
    args = parse_args()
    mb = Path(args.mbtiles)
    if not mb.exists():
        raise SystemExit(f"MBTiles not found: {mb}")

    print(f"Loading MBTiles tiles from {mb}...")
    mbtiles_tiles = read_mbtiles_tiles(mb)
    print(f"MBTiles contains {len(mbtiles_tiles)} tiles")

    print("Loading source bounds and generating reference tiles (this may take a while)...")
    records = load_bounds(args.source)

    gen = generate_aggregated_tiles(
        records=records,
        min_zoom=args.min_zoom,
        max_zoom=args.max_zoom,
        bbox_wgs84=tuple(args.bbox),
        progress_interval=0,
        verbose=False,
    )

    ref_tiles = {}
    for z, x, y, webp in gen:
        ref_tiles[(z, x, y)] = webp

    print(f"Reference generator produced {len(ref_tiles)} tiles")

    # Compare sets
    mismatches = 0
    missing_in_mb = 0
    for key, ref in ref_tiles.items():
        mbdata = mbtiles_tiles.get(key)
        if mbdata is None:
            missing_in_mb += 1
            continue
        if mbdata != ref:
            mismatches += 1

    extra_in_mb = len(mbtiles_tiles) - len(ref_tiles) + missing_in_mb

    print(f"Comparison results:")
    print(f"  ref tiles: {len(ref_tiles)}")
    print(f"  mbtiles tiles: {len(mbtiles_tiles)}")
    print(f"  missing in mbtiles: {missing_in_mb}")
    print(f"  mismatched bytes: {mismatches}")
    print(f"  extra in mbtiles: {extra_in_mb}")

    if mismatches == 0 and missing_in_mb == 0:
        print("MBTiles tiles match generator output (including correct y-flip handling).")
    else:
        print("Discrepancies detected. See counts above.")


if __name__ == '__main__':
    main()
