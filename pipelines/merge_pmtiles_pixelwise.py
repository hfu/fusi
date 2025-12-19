#!/usr/bin/env python3
"""Direct PMTiles output by pixel-wise merging multiple Terrarium MBTiles.

This reads tiles from multiple MBTiles (input order defines priority) and
writes a PMTiles archive directly without creating intermediate MBTiles.

Default mode is 'priority' (first-available tile wins). 'max' computes
per-pixel maximum elevation across available tiles.

Memory: operates per-tile (512x512) so RAM usage is low; I/O is heavier
because many small reads from input SQLite files occur.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import List, Optional, Set, Tuple

import numpy as np

try:
    import mercantile
except Exception:
    mercantile = None

from pmtiles.tile import zxy_to_tileid, TileType, Compression
from pmtiles.writer import Writer

from . import imagecodecs
from .convert_terrarium import encode_terrarium


def read_tile_blob(conn: sqlite3.Connection, z: int, x: int, y: int) -> Optional[bytes]:
    tms_y = (1 << z) - 1 - y
    cur = conn.execute(
        "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
        (z, x, tms_y),
    )
    row = cur.fetchone()
    return row[0] if row else None


def terrarium_to_elevation(arr: np.ndarray) -> np.ndarray:
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError("Unexpected tile shape for Terrarium decoding")
    r = arr[..., 0].astype(np.float32)
    g = arr[..., 1].astype(np.float32)
    b = arr[..., 2].astype(np.float32)
    elev = (r * 256.0) + g + (b / 256.0) - 32768.0
    return elev


def gather_zoom_keys(conns: List[sqlite3.Connection], z: int) -> Set[Tuple[int, int, int]]:
    keys = set()
    for conn in conns:
        cur = conn.execute("SELECT tile_column, tile_row FROM tiles WHERE zoom_level=?", (z,))
        for x, tms_y in cur:
            y = (1 << z) - 1 - tms_y
            keys.add((z, x, y))
    return keys


def get_min_max_zoom(conns: List[sqlite3.Connection]) -> Tuple[int, int]:
    minz = 999
    maxz = -1
    for conn in conns:
        cur = conn.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles")
        r = cur.fetchone()
        if r:
            lo, hi = r
            if lo is not None:
                minz = min(minz, int(lo))
            if hi is not None:
                maxz = max(maxz, int(hi))
    if maxz < 0:
        raise RuntimeError("No tiles found in inputs")
    if minz == 999:
        minz = 0
    return minz, maxz


def write_pmtiles_from_mbtiles(
    input_paths: List[Path], output_path: Path, mode: str = "priority", verbose: bool = True
) -> None:
    conns = [sqlite3.connect(str(p)) for p in input_paths]
    try:
        minz, maxz = get_min_max_zoom(conns)

        spool_dir = str(output_path.parent)
        # Track bounds for metadata
        min_lon = float("inf")
        min_lat = float("inf")
        max_lon = float("-inf")
        max_lat = float("-inf")
        min_z = 999
        max_z = -1

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            writer = Writer(f)

            for z in range(minz, maxz + 1):
                keys = gather_zoom_keys(conns, z)
                if not keys:
                    continue
                if verbose:
                    print(f"Processing z{z}: {len(keys)} tiles")

                for (_, x, y) in sorted(keys):
                    # Collect tile blobs in input priority order
                    blobs = [read_tile_blob(c, z, x, y) for c in conns]
                    if all(b is None for b in blobs):
                        continue

                    if mode == "priority":
                        chosen_blob = next((b for b in blobs if b is not None), None)
                        if chosen_blob is None:
                            continue
                        try:
                            arr = imagecodecs.webp_decode(chosen_blob)
                            elev = terrarium_to_elevation(arr)
                        except Exception:
                            # If decode fails, skip
                            continue
                    else:
                        elevs = []
                        for b in blobs:
                            if b is None:
                                continue
                            try:
                                arr = imagecodecs.webp_decode(b)
                                elevs.append(terrarium_to_elevation(arr))
                            except Exception:
                                continue
                        if not elevs:
                            continue
                        stacked = np.stack(elevs, axis=0)
                        elev = np.nanmax(stacked, axis=0)

                    # Encode to Terrarium RGB and write as WebP
                    try:
                        rgb = encode_terrarium(elev, z)
                        webp = imagecodecs.webp_encode(rgb, lossless=True)
                    except Exception as exc:
                        if verbose:
                            print(f"Warning: failed to encode tile z{z}/x{x}/y{y}: {exc}")
                        continue

                    # update bounds
                    if mercantile is not None:
                        try:
                            b = mercantile.bounds(x, y, z)
                            min_lon = min(min_lon, b.west)
                            min_lat = min(min_lat, b.south)
                            max_lon = max(max_lon, b.east)
                            max_lat = max(max_lat, b.north)
                        except Exception:
                            pass
                    min_z = min(min_z, z)
                    max_z = max(max_z, z)

                    tile_id = zxy_to_tileid(z=z, x=x, y=y)
                    writer.write_tile(tile_id, webp)

            # Finalize metadata
            metadata = {
                "tile_type": TileType.WEBP,
                "tile_compression": Compression.NONE,
                "min_zoom": min_z if min_z != 999 else minz,
                "max_zoom": max_z if max_z != -1 else maxz,
            }
            if mercantile is not None and min_lon != float("inf"):
                metadata.update(
                    {
                        "min_lon_e7": int(min_lon * 1e7),
                        "min_lat_e7": int(min_lat * 1e7),
                        "max_lon_e7": int(max_lon * 1e7),
                        "max_lat_e7": int(max_lat * 1e7),
                        "center_zoom": int(0.5 * ((metadata["min_zoom"] + metadata["max_zoom"]))),
                        "center_lon_e7": int(0.5 * (int(min_lon * 1e7) + int(max_lon * 1e7))),
                        "center_lat_e7": int(0.5 * (int(min_lat * 1e7) + int(max_lat * 1e7))),
                    }
                )

            writer.finalize(metadata, {"encoding": "terrarium", "attribution": "国土地理院 (GSI Japan)"})
            if verbose:
                print(f"Wrote PMTiles: {output_path}")

    finally:
        for c in conns:
            try:
                c.close()
            except Exception:
                pass


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge multiple MBTiles into PMTiles (pixel-wise)")
    parser.add_argument("inputs", nargs='+', help="Input MBTiles files in priority order")
    parser.add_argument("-o", "--output", required=True, help="Output PMTiles path")
    parser.add_argument("--mode", choices=["priority", "max"], default="priority", help="Merge mode")
    parser.add_argument("--verbose", action='store_true', help="Verbose output")
    args = parser.parse_args(argv)

    inputs = [Path(p) for p in args.inputs]
    out = Path(args.output)
    write_pmtiles_from_mbtiles(inputs, out, mode=args.mode, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
