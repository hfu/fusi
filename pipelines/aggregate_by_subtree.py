#!/usr/bin/env python3
"""Prototype: aggregate_by_subtree

This module provides a simple driver to run aggregate for geographic subtrees
corresponding to a given z6 tile (or multiple z6 tiles). The goal is to
produce a lightweight, testable implementation that:

- Accepts a z6 tile coordinate (z=6, x, y) or list of them
- Computes the corresponding bbox in WGS84
- Invokes existing aggregate_by_zoom / aggregate_pmtiles functionality to
  produce an MBTiles for that subtree

This is intentionally minimal: it wires existing functions and provides
naming conventions and a predictable output layout for subsequent merging.

Usage examples (shell):

    pipenv run python -m pipelines.aggregate_by_subtree --tile 6/12/20 \
        --output-dir output/subtrees

    pipenv run python -m pipelines.aggregate_by_subtree --tile 6/12/20 --tile 6/13/20 \
        --output-dir output/subtrees --max-zoom 16

"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple, List

import mercantile

# Import existing aggregate runner if available
try:
    from pipelines.aggregate_by_zoom import aggregate_zoom_range
except Exception:
    aggregate_zoom_range = None


def z6_tile_to_bbox_wgs84(x: int, y: int) -> Tuple[float, float, float, float]:
    """Return bbox (west, south, east, north) in WGS84 for z=6 tile x,y.

    Uses the full extent of the z6 tile (i.e. the tile's lon/lat bounds).
    """
    # mercantile.bounds accepts (x, y, z)
    b = mercantile.bounds(x, y, 6)
    return (b.west, b.south, b.east, b.north)


def run_subtree_aggregate(
    sources: List[str],
    out_base: Path,
    z6_tiles: List[Tuple[int, int]],
    min_zoom: int = 0,
    max_zoom: int = 16,
    keep_intermediates: bool = False,
) -> List[Path]:
    """Run aggregate for each z6 tile and produce MBTiles paths.

    Returns list of generated MBTiles paths.

    This function is a thin orchestration layer: it computes bboxes and calls
    `aggregate_zoom_range` if available. If that function is not imported,
    it will raise an error and the caller should run their own aggregation
    command (e.g. via `just` or the existing CLI).
    """
    out_paths: List[Path] = []
    out_base.mkdir(parents=True, exist_ok=True)

    if aggregate_zoom_range is None:
        raise RuntimeError("aggregate_zoom_range is not available in pipelines")

    for x, y in z6_tiles:
        bbox = z6_tile_to_bbox_wgs84(x, y)
        name = f"subtree_z6_x{x}_y{y}_z{min_zoom}-{max_zoom}.mbtiles"
        out_path = out_base / name
        print(f"[subtree] Aggregating z6 tile x={x} y={y} bbox={bbox} -> {out_path}")

        # Call existing aggregate API. We assume signature similar to
        # aggregate_zoom_range(records, output_mbtiles, min_zoom, max_zoom, bbox_wgs84=...)
        aggregate_zoom_range(
            sources,
            out_path,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            bbox_wgs84=bbox,
        )

        out_paths.append(out_path)

        if not keep_intermediates:
            # Placeholder: aggregate_zoom_range should write only the MBTiles we want
            pass

    return out_paths


def parse_tile_arg(tile_str: str) -> Tuple[int, int]:
    # Accept forms: "6/12/20" or "12/20" (x/y) assuming z=6
    if tile_str.count("/") == 2:
        z, x, y = tile_str.split("/")
        z = int(z)
        if z != 6:
            raise ValueError("Only z=6 tiles are supported by this prototype")
        return (int(x), int(y))
    elif tile_str.count("/") == 1:
        x, y = tile_str.split("/")
        return (int(x), int(y))
    else:
        raise ValueError("Tile must be in form '6/x/y' or 'x/y' for z6 tiles")


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tile", action="append", help="z6 tile, e.g. 6/12/20 or 12/20", required=True)
    p.add_argument("--output-dir", help="Directory to write subtree MBTiles", required=True)
    p.add_argument("--min-zoom", type=int, default=0)
    p.add_argument("--max-zoom", type=int, default=16)
    p.add_argument("--source", action="append", help="Source names (source-store/<name>)", required=True)
    p.add_argument("--keep-intermediates", action="store_true")

    args = p.parse_args(argv)

    tiles = [parse_tile_arg(t) for t in args.tile]
    out_base = Path(args.output_dir)
    sources = args.source

    try:
        generated = run_subtree_aggregate(sources, out_base, tiles, args.min_zoom, args.max_zoom, args.keep_intermediates)
    except Exception as e:
        print(f"Error during subtree aggregation: {e}")
        return 2

    print("Generated MBTiles:")
    for pth in generated:
        print(" - ", pth)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
