#!/usr/bin/env python3
"""指定されたズーム範囲でaggregate処理を実行するモジュール。

既存のaggregate_pmtiles.pyの機能を拡張し、ズーム範囲を指定して
部分的なMBTilesを生成します。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from .aggregate_pmtiles import (
    build_records_from_sources,
    compute_max_zoom_for_records,
    run_aggregate,
    SourceRecord,
    MAX_SUPPORTED_ZOOM,
)


def aggregate_zoom_range(
    records: Sequence[SourceRecord],
    output_mbtiles: Union[str, Path],
    min_zoom: int,
    max_zoom: int,
    bbox_wgs84: Optional[Tuple[float, float, float, float]] = None,
    progress_interval: int = 500,
    verbose: bool = False,
    io_sleep_ms: int = 0,
    warp_threads: int = 1,
    overwrite: bool = False,
) -> Path:
    """指定されたズーム範囲でaggregate処理を実行する。

    この関数は既存のrun_aggregateを内部で使用し、指定されたズーム範囲のみを
    処理します。PMTiles変換はスキップし、MBTilesのみを生成します。

    Args:
        records: ソースレコードのリスト
        output_mbtiles: 出力MBTilesファイルのパス
        min_zoom: 最小ズームレベル
        max_zoom: 最大ズームレベル
        bbox_wgs84: バウンディングボックス (west, south, east, north)
        progress_interval: 進捗表示の間隔
        verbose: 詳細なログを出力するか
        io_sleep_ms: タイルごとのスリープ時間（ミリ秒）
        warp_threads: warpスレッド数
        overwrite: 既存ファイルを上書きするか

    Returns:
        生成されたMBTilesファイルのパス
    """
    mbtiles_path = Path(output_mbtiles)

    # 拡張子を.mbtilsに強制
    if mbtiles_path.suffix != ".mbtiles":
        mbtiles_path = mbtiles_path.with_suffix(".mbtiles")

    if verbose:
        print(f"\n{'='*60}")
        print(f"Aggregate for zoom range: z{min_zoom}-{max_zoom}")
        print(f"Output: {mbtiles_path}")
        print(f"{'='*60}\n")

    # run_aggregateを使用（PMTiles変換なしのためダミーパスを指定）
    # 実際にはMBTilesのみが生成される
    dummy_pmtiles = mbtiles_path.with_suffix(".pmtiles.tmp")

    result_mbtiles = run_aggregate(
        records=records,
        output_pmtiles=dummy_pmtiles,  # ダミー（実際にはMBTilesのみ生成）
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        bbox_wgs84=bbox_wgs84,
        progress_interval=progress_interval,
        verbose=verbose,
        io_sleep_ms=io_sleep_ms,
        warp_threads=warp_threads,
        overwrite=overwrite,
        emit_lineage=False,  # lineageは無効化
        lineage_suffix="",
    )

    # 生成されたMBTilesを目的のパスに移動
    if result_mbtiles != mbtiles_path:
        if mbtiles_path.exists() and overwrite:
            mbtiles_path.unlink()
        result_mbtiles.rename(mbtiles_path)

    # ダミーのPMTilesファイルが生成されていれば削除
    if dummy_pmtiles.exists():
        dummy_pmtiles.unlink()

    if verbose:
        print(f"\n{'='*60}")
        print(f"Zoom range aggregate completed: {mbtiles_path}")
        print(f"{'='*60}\n")

    return mbtiles_path


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="Aggregate GeoTIFFs for a specific zoom range into MBTiles",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output MBTiles path",
    )
    parser.add_argument(
        "--min-zoom",
        type=int,
        required=True,
        help="Minimum zoom level",
    )
    parser.add_argument(
        "--max-zoom",
        type=int,
        required=True,
        help="Maximum zoom level",
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Optional WGS84 bounding box to limit the export (degrees)",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=200,
        help="Tile interval for printing progress updates",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress verbose logging during aggregation",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging (overrides --silent)",
    )
    parser.add_argument(
        "--io-sleep-ms",
        type=int,
        default=1,
        help="Sleep for the given milliseconds per emitted tile",
    )
    parser.add_argument(
        "--warp-threads",
        type=int,
        default=1,
        help="Number of threads for raster warping",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing MBTiles output if present",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        help="One or more source names under source-store/",
    )

    args = parser.parse_args()

    # ズームレベルの検証
    if args.min_zoom < 0 or args.max_zoom < 0:
        parser.error("Zoom levels must be non-negative")
    if args.min_zoom > args.max_zoom:
        parser.error("min_zoom cannot be larger than max_zoom")
    if args.max_zoom > MAX_SUPPORTED_ZOOM:
        parser.error(f"max_zoom exceeds supported maximum ({MAX_SUPPORTED_ZOOM})")

    # verbose/silentの解決
    if args.verbose:
        args.verbose = True
    else:
        args.verbose = not args.silent

    return args


def main() -> None:
    """CLIエントリーポイント。"""
    args = parse_args()

    if not args.sources:
        raise SystemExit("At least one source name is required")

    # ソースレコードを構築
    records = build_records_from_sources(args.sources)

    if args.verbose:
        print(f"Loaded {len(records)} source records from {len(args.sources)} source(s)")

    # バウンディングボックス
    bbox = tuple(args.bbox) if args.bbox else None

    # aggregate実行
    try:
        output_path = aggregate_zoom_range(
            records=records,
            output_mbtiles=args.output,
            min_zoom=args.min_zoom,
            max_zoom=args.max_zoom,
            bbox_wgs84=bbox,
            progress_interval=args.progress_interval,
            verbose=args.verbose,
            io_sleep_ms=args.io_sleep_ms,
            warp_threads=args.warp_threads,
            overwrite=args.overwrite,
        )
        print(f"Success! Output: {output_path}")
    except Exception as e:
        print(f"Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
