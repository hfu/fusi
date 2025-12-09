import sqlite3
import tempfile
from pathlib import Path
import os

from pipelines.merge_mbtiles import merge_mbtiles_files, get_mbtiles_metadata


def _create_mbtiles(path: Path, zoom: int, x: int, y_tms: int, tile_data: bytes = b"x"):
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=DELETE;
            CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS tiles (
                zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB,
                UNIQUE(zoom_level, tile_column, tile_row)
            );
            """
        )
        conn.execute("INSERT OR REPLACE INTO metadata (name, value) VALUES (?,?)", ("name", path.stem))
        conn.execute(
            "INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?,?,?,?)",
            (zoom, x, y_tms, sqlite3.Binary(tile_data)),
        )
        conn.commit()
    finally:
        conn.close()


def test_merge_two_small_mbtiles(tmp_path):
    a = tmp_path / "a.mbtiles"
    b = tmp_path / "b.mbtiles"
    out = tmp_path / "out.mbtiles"

    # create two MBTiles with non-overlapping tiles
    _create_mbtiles(a, 5, 10, (1 << 5) - 1 - 12)
    _create_mbtiles(b, 6, 20, (1 << 6) - 1 - 15)

    merge_mbtiles_files([a, b], out, verify_overlaps=True, overwrite=True, verbose=False)

    assert out.exists()
    md = get_mbtiles_metadata(out)
    assert md.get("name") == "a" or md.get("name") == "out"
    # minzoom and maxzoom should be present
    assert "minzoom" in md and "maxzoom" in md


def test_overlap_detection(tmp_path):
    a = tmp_path / "a.mbtiles"
    b = tmp_path / "b.mbtiles"
    out = tmp_path / "out.mbtiles"

    # create two MBTiles with overlapping tile (same z/x/y)
    z = 5
    x = 10
    y_tms = (1 << z) - 1 - 12
    _create_mbtiles(a, z, x, y_tms)
    # create b with the same tile
    _create_mbtiles(b, z, x, y_tms)

    try:
        merge_mbtiles_files([a, b], out, verify_overlaps=True, overwrite=True, verbose=False)
        raised = False
    except ValueError:
        raised = True

    assert raised, "Expected merge to raise ValueError due to overlapping tiles"
