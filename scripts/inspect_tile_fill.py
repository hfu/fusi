#!/usr/bin/env python3
"""Inspect a single tile from MBTiles and compare against individual sources.

Usage:
  python scripts/inspect_tile_fill.py --mbtiles output/shimabara.mbtiles --z 8 --x 220 --y 152 --sources dem1a dem10b

Prints per-source availability and whether lower-priority source filled nodata from higher-priority source.
"""

from __future__ import annotations

import sqlite3
import sys
from io import BytesIO
from pathlib import Path
import argparse

import numpy as np
from PIL import Image

# Import helpers from pipelines
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.aggregate_pmtiles import (
    load_bounds,
    read_tile_from_source,
    merge_tile_candidates,
)
import mercantile
from pipelines import imagecodecs


def decode_webp_to_elevation(webp_bytes: bytes) -> np.ndarray:
    # Decode WebP to RGB(A) using imagecodecs if available, fallback to Pillow
    try:
        arr = imagecodecs.webp_decode(webp_bytes)
        # imagecodecs returns ndarray uint8 with shape (h,w,3) or (h,w,4)
        rgb = arr[:, :, :3]
    except Exception:
        img = Image.open(BytesIO(webp_bytes)).convert("RGB")
        rgb = np.array(img)

    r = rgb[:, :, 0].astype("float32")
    g = rgb[:, :, 1].astype("float32")
    b = rgb[:, :, 2].astype("float32")
    elev = (r * 256.0 + g + b / 256.0) - 32768.0
    return elev


def fetch_tile_from_mbtiles(mbtiles_path: Path, z: int, x: int, y: int) -> bytes | None:
    conn = sqlite3.connect(str(mbtiles_path))
    try:
        # MBTiles stores tile_row in TMS (flipped Y). Try TMS first, then XYZ as fallback.
        tms_y = (1 << z) - 1 - y
        cur = conn.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, tms_y),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        # Fallback: perhaps the DB stored XYZ directly
        cur = conn.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, y),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        return None
    finally:
        conn.close()


def assemble_source_tile(source_name: str, z: int, x: int, y: int, warp_threads: int = 1):
    records = load_bounds(source_name, priority=0)
    # Accept the provided (x,y) as XYZ. However MBTiles stores TMS, and
    # earlier runs may have mixed conventions. Try both XYZ and TMS-derived
    # bounds when searching for overlapping source records.
    tile_xyz = mercantile.Tile(x=x, y=y, z=z)
    bounds_xyz = mercantile.xy_bounds(tile_xyz)
    # TMS interpretation of y
    y_tms = (1 << z) - 1 - y
    tile_tms = mercantile.Tile(x=x, y=y_tms, z=z)
    bounds_tms = mercantile.xy_bounds(tile_tms)
    candidates = []
    for rec in records:
        left, bottom, right, top = rec.bounds_mercator
        # Check intersection against both interpretations
        overlap_xyz = not (right <= bounds_xyz.left or left >= bounds_xyz.right or top <= bounds_xyz.bottom or bottom >= bounds_xyz.top)
        overlap_tms = not (right <= bounds_tms.left or left >= bounds_tms.right or top <= bounds_tms.bottom or bottom >= bounds_tms.top)
        if not (overlap_xyz or overlap_tms):
            continue
        try:
            # Prefer XYZ bounds for reprojection; fallback to TMS if needed
            arr = read_tile_from_source(rec, bounds_xyz if overlap_xyz else bounds_tms, out_shape=(512, 512), warp_threads=warp_threads)
        except Exception as exc:
            print(f"Warning reading {rec.path}: {exc}")
            continue
        if arr is not None:
            candidates.append(arr)
    if not candidates:
        return None
    merged = merge_tile_candidates(candidates)
    return merged


def summarize_and_compare(mbtiles_path: Path, z: int, x: int, y: int, sources: list[str]):
    print(f"Inspecting tile z={z} x={x} y={y} from {mbtiles_path}")
    webp = fetch_tile_from_mbtiles(mbtiles_path, z, x, y)
    if webp is None:
        print("No tile found in MBTiles.")
        return 1

    mb_elev = decode_webp_to_elevation(webp)

    source_elevs = {}
    for src in sources:
        merged = assemble_source_tile(src, z, x, y, warp_threads=1)
        source_elevs[src] = merged
        valid = None if merged is None else (~np.isnan(merged))
        valid_count = 0 if merged is None else int(np.count_nonzero(valid))
        print(f"Source {src}: {'no coverage' if merged is None else f'has data, valid pixels={valid_count}'}")

    # Now check if MBTiles shows areas that came from lower-priority sources
    # We'll assume sources are ordered by priority (higher priority first)
    base = source_elevs[sources[0]] if sources and sources[0] in source_elevs else None
    if base is None:
        print("Top-priority source has no coverage for this tile; MBTiles likely uses lower-priority source.")
    else:
        base_mask = ~np.isnan(base)
        mb_mask = ~np.isnan(mb_elev)
        # Pixels where base is NaN but MB has value -> filled from lower-priority
        filled_mask = np.isnan(base) & (~np.isnan(mb_elev))
        filled_count = int(np.count_nonzero(filled_mask))
        total_pixels = mb_elev.size
        pct = filled_count / total_pixels * 100.0
        print(f"Pixels filled by lower-priority sources: {filled_count}/{total_pixels} ({pct:.4f}%)")

        # For diagnostics also report where MB differs from top source where both valid
        both_valid = base_mask & mb_mask
        if np.count_nonzero(both_valid) > 0:
            diff = np.abs(mb_elev[both_valid] - base[both_valid])
            mean_diff = float(np.mean(diff))
            max_diff = float(np.max(diff))
            print(f"Where both valid: mean abs diff={mean_diff:.4f} m, max diff={max_diff:.4f} m")

    # If there are at least two sources, also check lower-priority contribution
    if len(sources) >= 2:
        lower = source_elevs[sources[1]]
        if lower is None:
            print(f"Lower-priority source {sources[1]} has no coverage for this tile.")
        else:
            lower_mask = ~np.isnan(lower)
            contrib_mask = np.isnan(source_elevs[sources[0]] if source_elevs[sources[0]] is not None else np.full(mb_elev.shape, np.nan)) & lower_mask
            contrib_count = int(np.count_nonzero(contrib_mask))
            print(f"Lower-priority source provides {contrib_count} pixels (candidate fill) in its own assembled tile")

    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mbtiles", required=True)
    parser.add_argument("--z", type=int, required=True)
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y", type=int, required=True)
    parser.add_argument("--sources", nargs="+", required=True)
    args = parser.parse_args()

    mb = Path(args.mbtiles)
    if not mb.exists():
        print(f"MBTiles not found: {mb}")
        raise SystemExit(2)

    rc = summarize_and_compare(mb, args.z, args.x, args.y, args.sources)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
