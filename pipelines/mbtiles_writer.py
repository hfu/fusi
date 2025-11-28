#!/usr/bin/env python3
"""Helpers to write Terrarium WebP tiles into an MBTiles (SQLite) file.

This is intentionally minimal and focused on the specific needs of the
aggregation pipeline:

* Tiles table with (zoom_level, tile_column, tile_row, tile_data)
* `tile_row` uses the MBTiles convention (TMS-style, flipped Y).
* A small `metadata` table with the essential fields for go-pmtiles.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Generator, Iterable, Tuple

import mercantile


class MBTilesWriter:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        # Use WAL for better concurrent/writing performance, but keep
        # synchronous at NORMAL to balance durability and speed.
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA temp_store=MEMORY;")
        # Let SQLite perform periodic auto-checkpoints; we also perform
        # explicit checkpoints every N inserted tiles to keep .wal bounded.
        try:
            self.conn.execute("PRAGMA wal_autocheckpoint=1000;")
        except Exception:
            pass
        self._ensure_schema()

        # Insert bookkeeping to enable periodic WAL checkpointing
        self._insert_count = 0
        # Default checkpoint interval (number of tiles). Tuneable.
        self._checkpoint_interval = 10000

        # Track basic bounds and zoom range while writing tiles
        self._min_z = math.inf
        self._max_z = -math.inf
        self._min_lon = math.inf
        self._min_lat = math.inf
        self._max_lon = -math.inf
        self._max_lat = -math.inf

    def _ensure_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                name TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS tiles (
                zoom_level INTEGER,
                tile_column INTEGER,
                tile_row INTEGER,
                tile_data BLOB,
                UNIQUE(zoom_level, tile_column, tile_row)
            );

            CREATE INDEX IF NOT EXISTS idx_tiles_zxy
                ON tiles(zoom_level, tile_column, tile_row);
            """
        )
        self.conn.commit()

    def _update_bounds(self, z: int, x: int, y: int) -> None:
        self._min_z = min(self._min_z, z)
        self._max_z = max(self._max_z, z)
        bounds = mercantile.bounds(x, y, z)
        self._min_lon = min(self._min_lon, bounds.west)
        self._min_lat = min(self._min_lat, bounds.south)
        self._max_lon = max(self._max_lon, bounds.east)
        self._max_lat = max(self._max_lat, bounds.north)

    def add_tiles(self, tiles: Iterable[Tuple[int, int, int, bytes]], batch_size: int = 1000) -> None:
        """Insert tiles into the MBTiles file.

        `tiles` must yield (z, x, y, data) where (z, x, y) are XYZ.
        """

        cur = self.conn.cursor()
        batch = []
        for z, x, y, data in tiles:
            # MBTiles uses TMS Y (flipped from XYZ)
            tms_y = (1 << z) - 1 - y
            batch.append((z, x, tms_y, sqlite3.Binary(data)))
            self._update_bounds(z, x, y)

            # Track total inserts and periodically checkpoint to avoid
            # an unbounded WAL file during long-running writes.
            self._insert_count += 1

            if len(batch) >= batch_size:
                cur.executemany(
                    "INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                    batch,
                )
                self.conn.commit()
                if self._insert_count and (self._insert_count % self._checkpoint_interval) == 0:
                    try:
                        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                        self.conn.commit()
                    except Exception:
                        # Non-fatal; we'll try again at finalize
                        pass
                batch.clear()

        if batch:
            cur.executemany(
                "INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                batch,
            )
            self.conn.commit()
            if self._insert_count and (self._insert_count % self._checkpoint_interval) == 0:
                try:
                    self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    self.conn.commit()
                except Exception:
                    pass

    def finalize(self, min_zoom: int | None = None, max_zoom: int | None = None) -> None:
        """Write minimal metadata and close the database."""

        if not math.isfinite(self._min_z) or not math.isfinite(self._max_z):
            # No tiles written; nothing to finalize.
            self.conn.close()
            return

        min_z = self._min_z if min_zoom is None else min_zoom
        max_z = self._max_z if max_zoom is None else max_zoom

        center_zoom = int(0.5 * (min_z + max_z))
        center_lon = 0.5 * (self._min_lon + self._max_lon)
        center_lat = 0.5 * (self._min_lat + self._max_lat)

        metadata = {
            "name": self.path.stem,
            "format": "webp",
            "bounds": f"{self._min_lon},{self._min_lat},{self._max_lon},{self._max_lat}",
            "minzoom": str(int(min_z)),
            "maxzoom": str(int(max_z)),
            "center": f"{center_lon},{center_lat},{center_zoom}",
            "attribution": "国土地理院 (GSI Japan)",
            "encoding": "terrarium",
        }

        cur = self.conn.cursor()
        cur.executemany(
            "INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)",
            list(metadata.items()),
        )
        # Final checkpoint and revert journal mode so that .wal/.shm are
        # removed when the DB is closed (if no other process has it open).
        try:
            self.conn.commit()
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            self.conn.execute("PRAGMA journal_mode=DELETE;")
            self.conn.commit()
        finally:
            try:
                self.conn.close()
            except Exception:
                pass


def create_mbtiles_from_tiles(
    tiles: Iterable[Tuple[int, int, int, bytes]],
    output_path: Path,
    batch_size: int = 1000,
) -> None:
    """Convenience wrapper: write all tiles into an MBTiles file.

    This mirrors the `create_pmtiles` interface but targets MBTiles instead.
    """

    import json

    # If the MBTiles already exists, remove it first to avoid accidental
    # appending duplicates from previous runs. If you want to preserve the
    # existing file, move it aside before calling this function.
    try:
        if output_path.exists():
            backup = output_path.with_suffix(output_path.suffix + ".bak")
            output_path.rename(backup)
    except Exception:
        # If renaming fails, fall back to removing the file
        try:
            output_path.unlink()
        except Exception:
            pass

    writer = MBTilesWriter(output_path)

    # Collect a small sample of mappings to verify Y-flip behaviour
    sample = []
    max_samples = 32

    def wrapping_generator(src_tiles):
        for idx, (z, x, y, data) in enumerate(src_tiles):
            if idx < max_samples:
                tms_y = (1 << z) - 1 - y
                sample.append({"z": z, "x": x, "y_xyz": y, "expected_tms_y": tms_y})
            yield z, x, y, data

    try:
        writer.add_tiles(wrapping_generator(tiles), batch_size=batch_size)
    except KeyboardInterrupt:
        # Ensure we write minimal metadata and close DB on user interrupt
        try:
            writer.finalize()
        except Exception:
            pass
        raise
    else:
        writer.finalize()

    # Write sample mapping next to MBTiles for inspection
    try:
        sample_path = output_path.with_suffix('.mbtiles.sample.json')
        with sample_path.open('w') as fp:
            json.dump(sample, fp, indent=2, ensure_ascii=False)
    except Exception:
        pass


__all__ = ["MBTilesWriter", "create_mbtiles_from_tiles"]
