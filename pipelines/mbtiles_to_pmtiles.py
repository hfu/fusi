#!/usr/bin/env python3
"""Convert MBTiles -> PMTiles using pmtiles.writer, ensuring correct TMS<->XYZ handling.

This script reads all entries from an MBTiles file, converts tile_row (TMS)
to XYZ y, computes tile_id via zxy_to_tileid, sorts by tile_id and writes a
PMTiles archive. It also prints a short sample of mappings for verification.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Tuple

from pmtiles.tile import zxy_to_tileid, TileType, Compression
from pmtiles.writer import Writer
import mercantile


def read_mbtiles_entries(path: Path) -> List[Tuple[int,int,int,bytes]]:
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.execute('SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles')
    out = []
    for z, x, tile_row, data in cur:
        y = (1 << z) - 1 - tile_row
        out.append((z, x, y, data))
    conn.close()
    return out


def write_pmtiles(entries: List[Tuple[int,int,int,bytes]], out_path: Path) -> None:
    # compute bounds and zoom range
    min_z = min(e[0] for e in entries)
    max_z = max(e[0] for e in entries)
    min_lon = min(mercantile.bounds(x,y,z).west for z,x,y,_ in entries)
    min_lat = min(mercantile.bounds(x,y,z).south for z,x,y,_ in entries)
    max_lon = max(mercantile.bounds(x,y,z).east for z,x,y,_ in entries)
    max_lat = max(mercantile.bounds(x,y,z).north for z,x,y,_ in entries)

    tiles_with_id = [(zxy_to_tileid(z,x,y), (z,x,y,data)) for (z,x,y,data) in entries]
    tiles_with_id.sort(key=lambda t: t[0])

    with open(out_path, 'wb') as f:
        writer = Writer(f)
        for tile_id, (zxy, xyz_data) in zip([t[0] for t in tiles_with_id], [t[1] for t in tiles_with_id]):
            # our tiles_with_id already contains ((z,x,y), data) in second element by construction above
            pass

    # Simpler loop to write using sorted list
    with open(out_path, 'wb') as f:
        writer = Writer(f)
        for tile_id, (z, x, y, data) in tiles_with_id:
            writer.write_tile(tile_id, data)

        writer.finalize(
            {
                'tile_type': TileType.WEBP,
                'tile_compression': Compression.NONE,
                'min_zoom': int(min_z),
                'max_zoom': int(max_z),
                'min_lon_e7': int(min_lon * 1e7),
                'min_lat_e7': int(min_lat * 1e7),
                'max_lon_e7': int(max_lon * 1e7),
                'max_lat_e7': int(max_lat * 1e7),
                'center_zoom': int(0.5 * (min_z + max_z)),
                'center_lon_e7': int(0.5 * (min_lon * 1e7 + max_lon * 1e7)),
                'center_lat_e7': int(0.5 * (min_lat * 1e7 + max_lat * 1e7)),
            },
            {
                'attribution': '国土地理院 (GSI Japan)',
                'encoding': 'terrarium',
            },
        )


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('mbtiles')
    p.add_argument('pmtiles')
    args = p.parse_args()

    mb = Path(args.mbtiles)
    pm = Path(args.pmtiles)
    entries = read_mbtiles_entries(mb)
    print(f"Read {len(entries)} entries from {mb}")
    # print sample mappings
    for z,x,y,_ in entries[:5]:
        print(f"sample tile xyz={z}/{x}/{y}")
    write_pmtiles(entries, pm)
    print(f"Wrote PMTiles to {pm}")


if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""Convert an MBTiles file to PMTiles using the Python pmtiles writer.

This is a small utility to avoid depending on an external `pmtiles` CLI
for smoke tests. It streams tiles from MBTiles (SQLite) and writes them
into a PMTiles archive using the pmtiles Python writer.
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
        # Best-effort: use metadata from MBTiles if available, otherwise leave defaults
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


def main(argv):
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
