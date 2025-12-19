#!/usr/bin/env python3
"""Pixel-wise merge of multiple Terrarium MBTiles into one MBTiles.

This tool reads tiles from multiple MBTiles (assumed Terrarium/WebP) and
produces a merged MBTiles by composing pixels. Two modes are supported:

- "max": take per-pixel maximum elevation across available tiles
- "priority": take the first available tile (tile-level priority)

Limitations:
- Terrarium encoding stores nodata as 0m (sea level) by design in this
  pipeline, so it is not possible to reliably detect nodata pixels from
  the encoded tile alone. The "max" mode typically acts as a sensible
  merger when sources partially overlap; "priority" implements a simple
  override semantics based on input order.

This implementation streams tiles and operates per-tile, keeping memory
usage low (one tile or a small stack of tiles in memory at a time).
"""

from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

import numpy as np

from . import imagecodecs
from .convert_terrarium import encode_terrarium
from .mbtiles_writer import create_mbtiles_from_tiles


def xyz_from_row(z: int, x: int, tms_y: int) -> Tuple[int, int, int]:
    y = (1 << z) - 1 - tms_y
    return z, x, y


def tiles_from_mbtiles(path: Path) -> Set[Tuple[int, int, int]]:
    keys: Set[Tuple[int, int, int]] = set()
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute("SELECT zoom_level, tile_column, tile_row FROM tiles")
        for z, x, tms_y in cur:
            keys.add(xyz_from_row(z, x, tms_y))
    finally:
        conn.close()
    return keys


def read_tile_blob(conn: sqlite3.Connection, z: int, x: int, y: int) -> Optional[bytes]:
    tms_y = (1 << z) - 1 - y
    cur = conn.execute(
        "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
        (z, x, tms_y),
    )
    row = cur.fetchone()
    return row[0] if row else None


def terrarium_to_elevation(arr: np.ndarray) -> np.ndarray:
    """Convert an RGB(A) uint8 array to elevation float array.

    Expect either (H,W,3) or (H,W,4); use the first three channels.
    """
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError("Unexpected tile shape for Terrarium decoding")
    r = arr[..., 0].astype(np.float32)
    g = arr[..., 1].astype(np.float32)
    b = arr[..., 2].astype(np.float32)
    elev = (r * 256.0) + g + (b / 256.0) - 32768.0
    return elev


def merge_tiles_pixelwise(
    mbtiles_paths: List[Path], mode: str = "max", verbose: bool = True
) -> Iterable[Tuple[int, int, int, bytes]]:
    """Yield merged tiles (z,x,y,webp_bytes) by pixel-wise composition.

    mode: 'max' or 'priority'
    """
    # Open DB connections
    conns = [sqlite3.connect(str(p)) for p in mbtiles_paths]

    try:
        # Collect union of tile keys
        if verbose:
            print("Scanning input MBTiles for tile keys...")
        all_keys: Set[Tuple[int, int, int]] = set()
        for p in mbtiles_paths:
            ks = tiles_from_mbtiles(p)
            all_keys.update(ks)
        if verbose:
            print(f"Total unique tiles to process: {len(all_keys)}")

        # Process tiles in sorted order by z,x,y for determinism
        for z, x, y in sorted(all_keys):
            tiles_stack: List[np.ndarray] = []
            for conn in conns:
                blob = read_tile_blob(conn, z, x, y)
                if not blob:
                    tiles_stack.append(None)
                else:
                    try:
                        arr = imagecodecs.webp_decode(blob)
                        tiles_stack.append(arr)
                    except Exception:
                        tiles_stack.append(None)

            # If no tile available at all, skip
            if all(t is None for t in tiles_stack):
                continue

            if mode == "priority":
                # Take first available tile (tile-level priority)
                chosen = next(t for t in tiles_stack if t is not None)
                # Convert to elevation and re-encode via Terrarium to normalize
                elev = terrarium_to_elevation(chosen)
            else:
                # 'max' mode: compute per-pixel max elevation
                elevs = []
                for t in tiles_stack:
                    if t is None:
                        continue
                    try:
                        elevs.append(terrarium_to_elevation(t))
                    except Exception:
                        continue
                if not elevs:
                    continue
                stacked = np.stack(elevs, axis=0)
                elev = np.nanmax(stacked, axis=0)

            # Encode Terrarium RGB at this zoom
            try:
                rgb = encode_terrarium(elev, z)
                webp = imagecodecs.webp_encode(rgb, lossless=True)
                yield z, x, y, webp
            except Exception as exc:
                if verbose:
                    print(f"Warning: failed to encode tile z{z}/x{x}/y{y}: {exc}")
                continue

    finally:
        for c in conns:
            try:
                c.close()
            except Exception:
                pass


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pixel-wise merge multiple Terrarium MBTiles")
    parser.add_argument("inputs", nargs='+', help="Input MBTiles files (order matters for priority)")
    parser.add_argument("-o", "--output", required=True, help="Output MBTiles path")
    parser.add_argument("--mode", choices=["max", "priority"], default="max", help="Merge mode")
    parser.add_argument("--verbose", action='store_true', help="Verbose output")
    args = parser.parse_args(argv)

    inputs = [Path(p) for p in args.inputs]
    out = Path(args.output)
    if out.exists():
        out.unlink()

    tiles_gen = merge_tiles_pixelwise(inputs, mode=args.mode, verbose=args.verbose)
    if args.verbose:
        print(f"Writing merged MBTiles: {out}")
    create_mbtiles_from_tiles(tiles_gen, out)
    if args.verbose:
        print("Pixel-wise merge completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
