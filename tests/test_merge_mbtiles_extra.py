import sqlite3
from pathlib import Path


def _create_empty_mbtiles(path: Path):
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=DELETE;
            CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS tiles (
                zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB
            );
            """
        )
        conn.execute("INSERT OR REPLACE INTO metadata (name, value) VALUES (?,?)", (path.stem, path.stem))
        conn.commit()
    finally:
        conn.close()


def _create_mbtiles_one_tile(path: Path, z: int, x: int, y_tms: int):
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
        conn.execute("INSERT OR REPLACE INTO metadata (name, value) VALUES (?,?)", (path.stem, path.stem))
        conn.execute(
            "INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?,?,?,?)",
            (z, x, y_tms, sqlite3.Binary(b"x")),
        )
        conn.commit()
    finally:
        conn.close()


def test_merge_with_empty_and_nonempty(tmp_path):
    a = tmp_path / "empty.mbtiles"
    b = tmp_path / "b.mbtiles"
    out = tmp_path / "out.mbtiles"

    _create_empty_mbtiles(a)
    # create one tile in b
    _create_mbtiles_one_tile(b, 5, 10, (1 << 5) - 1 - 12)

    # Import here to ensure we test the real function
    from pipelines.merge_mbtiles import merge_mbtiles_files, get_mbtiles_metadata

    merge_mbtiles_files([a, b], out, verify_overlaps=True, overwrite=True, verbose=False)

    assert out.exists()
    md = get_mbtiles_metadata(out)
    assert "minzoom" in md and "maxzoom" in md


def test_get_tile_stats_no_mercantile(tmp_path):
    # Ensure get_tile_stats works when mercantile is not available and returns bounds None
    p = tmp_path / "one.mbtiles"
    _create_mbtiles_one_tile(p, 6, 20, (1 << 6) - 1 - 15)

    from pipelines.merge_mbtiles import get_tile_stats, mercantile

    stats = get_tile_stats(p)
    # stats should report tile_count and zooms
    assert stats["tile_count"] == 1
    assert stats["min_zoom"] == 6
    assert stats["max_zoom"] == 6
    # bounds may be None if mercantile is not installed
    if mercantile is None:
        assert stats["bounds"] is None
    else:
        assert stats["bounds"] is not None
