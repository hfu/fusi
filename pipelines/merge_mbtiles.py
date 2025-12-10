#!/usr/bin/env python3
"""複数のMBTilesファイルをマージするモジュール。

Zoom分割で生成された複数のMBTilesファイルを1つのMBTilesファイルに
統合します。タイルの重複を検証し、メタデータを適切に更新します。
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    import mercantile  # optional; used for bounds calculation
except Exception:  # pragma: no cover - mercantile optional
    mercantile = None


def verify_no_overlaps(mbtiles_paths: List[Path], verbose: bool = True) -> Tuple[bool, List[str]]:
    """複数のMBTilesファイルにタイルの重複がないか検証する。

    Args:
        mbtiles_paths: 検証するMBTilesファイルのパスリスト
        verbose: 詳細なログを出力するか

    Returns:
        (重複なし, エラーメッセージリスト)のタプル
    """
    errors: List[str] = []
    # Delegate to helper that finds overlapping tiles and returns error messages
    overlaps = find_overlapping_tiles(mbtiles_paths, verbose=verbose)
    errors.extend(overlaps)

    if verbose:
        if errors:
            print(f"Found {len(errors)} overlap(s)")
        else:
            print("No overlaps found.")

    return (len(errors) == 0, errors)


def find_overlapping_tiles(mbtiles_paths: List[Path], verbose: bool = True) -> List[str]:
    """Scan MBTiles files and return a list of human-readable overlap error strings.

    This helper isolates the scanning logic so it can be unit-tested or reused
    independently from the boolean `verify_no_overlaps` wrapper.
    """
    errors: List[str] = []
    tile_locations: Dict[Tuple[int, int, int], Path] = {}

    for mbtiles_path in mbtiles_paths:
        if not mbtiles_path.exists():
            errors.append(f"File not found: {mbtiles_path}")
            continue

        if verbose:
            print(f"Checking {mbtiles_path.name}...")

        conn = sqlite3.connect(str(mbtiles_path))
        try:
            cur = conn.execute("SELECT zoom_level, tile_column, tile_row FROM tiles")
            for z, x, tms_y in cur:
                # MBTiles stores rows in TMS; convert to XYZ
                y = (1 << z) - 1 - tms_y
                key = (z, x, y)

                if key in tile_locations:
                    errors.append(
                        f"Duplicate tile at z{z}/x{x}/y{y}: "
                        f"found in both {tile_locations[key].name} and {mbtiles_path.name}"
                    )
                else:
                    tile_locations[key] = mbtiles_path
        finally:
            conn.close()

    return errors


def get_mbtiles_metadata(mbtiles_path: Path) -> Dict[str, str]:
    """MBTilesファイルからメタデータを取得する。

    Args:
        mbtiles_path: MBTilesファイルのパス

    Returns:
        メタデータの辞書
    """
    metadata = {}
    conn = sqlite3.connect(str(mbtiles_path))
    try:
        cur = conn.execute("SELECT name, value FROM metadata")
        for name, value in cur:
            metadata[name] = value
    finally:
        conn.close()
    return metadata


def get_tile_stats(mbtiles_path: Path) -> Dict[str, any]:
    """MBTilesファイルのタイル統計を取得する。

    Args:
        mbtiles_path: MBTilesファイルのパス

    Returns:
        統計情報の辞書（tile_count, min_zoom, max_zoom, bounds）
    """
    conn = sqlite3.connect(str(mbtiles_path))
    try:
        # タイル数
        cur = conn.execute("SELECT COUNT(*) FROM tiles")
        tile_count = cur.fetchone()[0]

        # ズーム範囲
        cur = conn.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles")
        min_zoom, max_zoom = cur.fetchone()
        # sqlite returns None when no rows; normalize to None
        if min_zoom is None:
            min_zoom = None
        if max_zoom is None:
            max_zoom = None

        # バウンディングボックス（XYZ座標で計算）。mercantileが利用可能なら詳細に計算。
        min_lon = math.inf
        min_lat = math.inf
        max_lon = -math.inf
        max_lat = -math.inf

        cur = conn.execute("SELECT zoom_level, tile_column, tile_row FROM tiles")
        for z, x, tms_y in cur:
            # TMS → XYZ変換
            y = (1 << z) - 1 - tms_y
            if mercantile is not None:
                try:
                    bounds = mercantile.bounds(x, y, z)
                    min_lon = min(min_lon, bounds.west)
                    min_lat = min(min_lat, bounds.south)
                    max_lon = max(max_lon, bounds.east)
                    max_lat = max(max_lat, bounds.north)
                except Exception:
                    # Fallback: skip bounds update if mercantile fails for some tile
                    pass
            else:
                # mercantile not available: skip bounds calculation
                pass

        bounds_out = None
        if tile_count > 0 and min_lon != math.inf and mercantile is not None:
            bounds_out = (min_lon, min_lat, max_lon, max_lat)

        return {
            "tile_count": tile_count,
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "bounds": bounds_out,
        }
    finally:
        conn.close()


def merge_mbtiles_files(
    input_paths: List[Path],
    output_path: Path,
    verify_overlaps: bool = True,
    overwrite: bool = False,
    verbose: bool = True,
) -> None:
    """複数のMBTilesファイルを1つにマージする。

    Args:
        input_paths: マージするMBTilesファイルのパスリスト
        output_path: 出力MBTilesファイルのパス
        verify_overlaps: マージ前に重複をチェックするか
        overwrite: 既存の出力ファイルを上書きするか
        verbose: 詳細なログを出力するか

    Raises:
        FileNotFoundError: 入力ファイルが存在しない場合
        FileExistsError: 出力ファイルが既に存在し、overwrite=Falseの場合
        ValueError: タイルに重複がある場合
    """
    # 入力ファイルの検証
    for path in input_paths:
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")

    # 出力ファイルの確認
    if output_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output file already exists: {output_path}. "
                f"Use --overwrite to replace it."
            )
        if verbose:
            print(f"Removing existing output file: {output_path}")
        output_path.unlink()

    # 重複チェック
    if verify_overlaps:
        if verbose:
            print("Verifying no overlaps between input files...")
        is_valid, errors = verify_no_overlaps(input_paths, verbose=verbose)
        if not is_valid:
            error_msg = "\n".join(errors)
            raise ValueError(f"Tile overlaps detected:\n{error_msg}")

    # 統計情報の収集
        if verbose:
            print("\nInput files:")
            for i, path in enumerate(input_paths, start=1):
                stats = get_tile_stats(path)
                zmin = stats['min_zoom'] if stats['min_zoom'] is not None else 'n/a'
                zmax = stats['max_zoom'] if stats['max_zoom'] is not None else 'n/a'
                print(
                    f"  {i}. {path.name}: {stats['tile_count']:,} tiles, z{zmin}-{zmax}"
                )

    # 出力MBTilesの作成
    output_path.parent.mkdir(parents=True, exist_ok=True)
    conn_out = sqlite3.connect(str(output_path))

    try:
        # スキーマの作成
        conn_out.execute("PRAGMA journal_mode=WAL;")
        conn_out.execute("PRAGMA synchronous=NORMAL;")
        conn_out.executescript(
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
        conn_out.commit()

        # タイルのマージ
        total_tiles = 0
        global_min_zoom = math.inf
        global_max_zoom = -math.inf
        global_min_lon = math.inf
        global_min_lat = math.inf
        global_max_lon = -math.inf
        global_max_lat = -math.inf

        for input_path in input_paths:
            if verbose:
                print(f"\nMerging tiles from {input_path.name}...")

            conn_in = sqlite3.connect(str(input_path))
            try:
                cur = conn_in.execute(
                    "SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles"
                )

                batch = []
                batch_size = 1000
                count = 0

                bounds_found = False
                for z, x, tms_y, data in cur:
                    batch.append((z, x, tms_y, sqlite3.Binary(data)))
                    count += 1

                    # TMS -> XYZ
                    y = (1 << z) - 1 - tms_y
                    # Update zoom extents regardless of mercantile availability
                    global_min_zoom = min(global_min_zoom, z)
                    global_max_zoom = max(global_max_zoom, z)

                    # Update bounds only if mercantile is available
                    if mercantile is not None:
                        try:
                            b = mercantile.bounds(x, y, z)
                            global_min_lon = min(global_min_lon, b.west)
                            global_min_lat = min(global_min_lat, b.south)
                            global_max_lon = max(global_max_lon, b.east)
                            global_max_lat = max(global_max_lat, b.north)
                            bounds_found = True
                        except Exception:
                            # skip bounds update for this tile
                            pass

                    if len(batch) >= batch_size:
                        conn_out.executemany(
                            "INSERT OR REPLACE INTO tiles "
                            "(zoom_level, tile_column, tile_row, tile_data) "
                            "VALUES (?, ?, ?, ?)",
                            batch,
                        )
                        conn_out.commit()
                        batch.clear()

                        if verbose and count % 10000 == 0:
                            print(f"  Merged {count:,} tiles...")

                # 残りのバッチを書き込み
                if batch:
                    conn_out.executemany(
                        "INSERT OR REPLACE INTO tiles "
                        "(zoom_level, tile_column, tile_row, tile_data) "
                        "VALUES (?, ?, ?, ?)",
                        batch,
                    )
                    conn_out.commit()

                total_tiles += count
                if verbose:
                    print(f"  Merged {count:,} tiles from {input_path.name}")

            finally:
                conn_in.close()

        # メタデータの書き込み
        # 各入力ファイルからメタデータを収集してマージ（attribution等は重複をまとめる）
        all_metadata: List[Dict[str, str]] = [get_mbtiles_metadata(p) for p in input_paths]

        # Prefer the first file's name/format/encoding, but merge attribution across inputs.
        base_metadata = all_metadata[0] if all_metadata else {}

        attributions: Set[str] = set()
        for md in all_metadata:
            a = md.get("attribution")
            if a:
                attributions.add(a.strip())

        combined_attribution = " | ".join(sorted(attributions)) if attributions else base_metadata.get("attribution", "国土地理院 (GSI Japan)")

        # If we couldn't determine global min/max zoom (no tiles), fall back to
        # first file's metadata values or omit.
        minzoom_val = (
            str(int(global_min_zoom)) if global_min_zoom != math.inf else base_metadata.get("minzoom")
        )
        maxzoom_val = (
            str(int(global_max_zoom)) if global_max_zoom != -math.inf else base_metadata.get("maxzoom")
        )

        if minzoom_val is None:
            minzoom_val = "0"
        if maxzoom_val is None:
            maxzoom_val = "0"

        merged_metadata = {
            "name": base_metadata.get("name", output_path.stem),
            "format": base_metadata.get("format", "webp"),
            "minzoom": minzoom_val,
            "maxzoom": maxzoom_val,
            "attribution": combined_attribution,
            "encoding": base_metadata.get("encoding", "terrarium"),
        }

        if 'bounds' in base_metadata and (global_min_lon == math.inf or global_max_lon == -math.inf):
            # If we couldn't compute bounds, fall back to first file's metadata bounds if present
            merged_metadata["bounds"] = base_metadata.get("bounds")
        elif global_min_lon != math.inf and global_max_lon != -math.inf:
            merged_metadata["bounds"] = f"{global_min_lon},{global_min_lat},{global_max_lon},{global_max_lat}"

        # center: only set if zooms are finite
        try:
            if global_min_zoom != math.inf and global_max_zoom != -math.inf:
                center_zoom = int((global_min_zoom + global_max_zoom) / 2.0)
                if 'bounds' in merged_metadata:
                    parts = merged_metadata["bounds"].split(',')
                    if len(parts) == 4:
                        center_lon = (float(parts[0]) + float(parts[2])) / 2.0
                        center_lat = (float(parts[1]) + float(parts[3])) / 2.0
                        merged_metadata["center"] = f"{center_lon},{center_lat},{center_zoom}"
        except Exception:
            # best-effort; if anything fails, skip center
            pass

        conn_out.executemany(
            "INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)",
            list(merged_metadata.items()),
        )

        # 最終化: WALをチェックポイントしてDELETEモードに戻す
        conn_out.commit()
        conn_out.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn_out.execute("PRAGMA journal_mode=DELETE;")
        conn_out.commit()

        if verbose:
            print(f"\nMerge completed successfully!")
            print(f"Output: {output_path}")
            print(f"Total tiles: {total_tiles:,}")
            # Zoom range
            if global_min_zoom != math.inf and global_max_zoom != -math.inf:
                print(f"Zoom range: z{int(global_min_zoom)}-{int(global_max_zoom)}")
            else:
                print("Zoom range: unknown")

            # Bounds
            if 'bounds' in merged_metadata:
                try:
                    parts = merged_metadata["bounds"].split(',')
                    print(
                        f"Bounds: {float(parts[0]):.4f},{float(parts[1]):.4f},"
                        f"{float(parts[2]):.4f},{float(parts[3]):.4f}"
                    )
                except Exception:
                    print(f"Bounds: {merged_metadata.get('bounds')}")
            else:
                print("Bounds: unknown")

    finally:
        conn_out.close()


def main() -> None:
    """CLIエントリーポイント。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Merge multiple MBTiles files into one",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output MBTiles file path",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input MBTiles files to merge",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip overlap verification (faster but risky)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    try:
        merge_mbtiles_files(
            input_paths=args.inputs,
            output_path=args.output,
            verify_overlaps=not args.no_verify,
            overwrite=args.overwrite,
            verbose=not args.silent,
        )
    except Exception as e:
        print(f"Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
