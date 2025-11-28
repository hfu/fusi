#!/usr/bin/env python3
"""Convert an MBTiles file to PMTiles using the Python `pmtiles` writer.

This utility is intended as an optional fallback when the `pmtiles convert`
CLI (go-pmtiles) is not available. It streams tiles from MBTiles (SQLite)
and writes them into a PMTiles archive using the Python `pmtiles.writer`.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Optional

from pmtiles.tile import zxy_to_tileid
from pmtiles.writer import Writer


def mbtiles_to_pmtiles(mbtiles_path: Path, pmtiles_path: Path) -> None:
    conn = sqlite3.connect(str(mbtiles_path))
    cur = conn.cursor()

    # Get basic metadata if present
    min_z: Optional[int] = None
    max_z: Optional[int] = None
    min_lon = None
    min_lat = None
    max_lon = None
    max_lat = None

    try:
        cur.execute("SELECT name, value FROM metadata")
        rows = cur.fetchall()
        meta = {name: value for name, value in rows}
        if 'minzoom' in meta:
            min_z = int(meta['minzoom'])
        if 'maxzoom' in meta:
            max_z = int(meta['maxzoom'])
        if 'bounds' in meta:
            parts = meta['bounds'].split(',')
            if len(parts) == 4:
                min_lon, min_lat, max_lon, max_lat = map(float, parts)
    except Exception:
        # No metadata table or entries; continue
        pass

    # Open PMTiles writer
    with open(pmtiles_path, 'wb') as f:
        writer = Writer(f)

        # Stream tiles ordered by zoom, column, row
        q = "SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles ORDER BY zoom_level, tile_column, tile_row"
        for z, x, tms_y, data in cur.execute(q):
            # Convert MBTiles TMS row to XYZ y
            y = (1 << z) - 1 - tms_y
            tile_id = zxy_to_tileid(z=z, x=x, y=y)
            writer.write_tile(tile_id, data)

        # Finalize metadata
        meta_out = {
            'tile_type': 'webp',
            'tile_compression': 'none',
            'encoding': 'terrarium',
            'attribution': '国土地理院 (GSI Japan)',
        }

        finalize_meta = {}
        if min_z is not None:
            finalize_meta['min_zoom'] = min_z
        if max_z is not None:
            finalize_meta['max_zoom'] = max_z
        if min_lon is not None and min_lat is not None and max_lon is not None and max_lat is not None:
            finalize_meta['min_lon_e7'] = int(min_lon * 1e7)
            finalize_meta['min_lat_e7'] = int(min_lat * 1e7)
            finalize_meta['max_lon_e7'] = int(max_lon * 1e7)
            finalize_meta['max_lat_e7'] = int(max_lat * 1e7)

        writer.finalize(finalize_meta, meta_out)

    conn.close()


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        print("Usage: mbtiles_to_pmtiles.py input.mbtiles output.pmtiles")
        raise SystemExit(2)
    mb = Path(argv[1])
    pm = Path(argv[2])
    if not mb.exists():
        print(f"MBTiles not found: {mb}")
        raise SystemExit(1)
    pm.parent.mkdir(parents=True, exist_ok=True)
    print(f"Converting {mb} -> {pm} (Python writer)")
    mbtiles_to_pmtiles(mb, pm)
    print("Conversion complete")


if __name__ == '__main__':
    main(sys.argv)
