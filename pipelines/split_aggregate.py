#!/usr/bin/env python3
"""Zoom分割を使ったaggregate処理の統合スクリプト。

メモリ使用量を抑えるために、ズームレベルを複数のグループに分割して
個別に処理し、最後にMBTilesをマージしてPMTilesに変換します。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .aggregate_by_zoom import aggregate_zoom_range
from .aggregate_pmtiles import build_records_from_sources, SourceRecord
from .merge_mbtiles import merge_mbtiles_files
from .zoom_split_config import (
    get_split_pattern,
    print_split_summary,
    validate_split_pattern,
    ZoomGroup,
)
from .memory_monitor import get_rss_bytes, format_bytes


def run_split_aggregate(
    sources: Sequence[str],
    output_pmtiles: Path,
    split_pattern: str = "balanced",
    resume_from: Optional[int] = None,
    bbox_wgs84: Optional[Tuple[float, float, float, float]] = None,
    progress_interval: int = 200,
    verbose: bool = True,
    io_sleep_ms: int = 1,
    warp_threads: int = 1,
    overwrite: bool = False,
    keep_intermediates: bool = False,
) -> None:
    """Zoom分割を使ったaggregate処理を実行する。

    Args:
        sources: ソース名のリスト
        output_pmtiles: 最終的なPMTilesファイルのパス
        split_pattern: 分割パターン名
        resume_from: 指定されたグループから再開（0ベース）
        bbox_wgs84: バウンディングボックス
        progress_interval: 進捗表示の間隔
        verbose: 詳細なログを出力するか
        io_sleep_ms: タイルごとのスリープ時間
        warp_threads: warpスレッド数
        overwrite: 既存ファイルを上書きするか
        keep_intermediates: 中間ファイルを保持するか
    """
    output_pmtiles = Path(output_pmtiles)
    output_dir = output_pmtiles.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # 分割パターンを取得
    groups = get_split_pattern(split_pattern)
    validate_split_pattern(groups)

    if verbose:
        print(f"\n{'='*70}")
        print("SPLIT AGGREGATE - Memory-Optimized Processing")
        print(f"{'='*70}")
        print(f"Output: {output_pmtiles}")
        print(f"Sources: {', '.join(sources)}")
        print_split_summary(groups)

    # ソースレコードを構築
    if verbose:
        print("Loading source records...")
    records = build_records_from_sources(sources)
    if verbose:
        print(f"Loaded {len(records)} source records\n")

    # 中間MBTilesファイルのパスリスト
    intermediate_mbtiles: List[Path] = []

    # 各グループを順次処理
    start_group = resume_from if resume_from is not None else 0

    for i, group in enumerate(groups):
        if i < start_group:
            # レジューム: スキップ
            intermediate_path = output_dir / f"{output_pmtiles.stem}_{group.name}.mbtiles"
            if intermediate_path.exists():
                intermediate_mbtiles.append(intermediate_path)
                if verbose:
                    print(f"Skipping group {i+1}/{len(groups)} (resume): {group.name}")
            else:
                raise FileNotFoundError(
                    f"Resume requested but intermediate file not found: {intermediate_path}"
                )
            continue

        if verbose:
            print(f"\n{'-'*70}")
            print(f"Processing group {i+1}/{len(groups)}: {group}")
            print(f"{'-'*70}\n")

        # Log memory before starting the group
        try:
            rss_before = get_rss_bytes()
            if verbose:
                print(f"Memory before group {i+1}: {format_bytes(rss_before)}")
        except Exception:
            rss_before = None

        group_start_time = time.time()

        # グループ用の中間MBTilesファイル
        intermediate_path = output_dir / f"{output_pmtiles.stem}_{group.name}.mbtiles"

        try:
            # ズーム範囲でaggregate実行
            aggregate_zoom_range(
                records=records,
                output_mbtiles=intermediate_path,
                min_zoom=group.min_zoom,
                max_zoom=group.max_zoom,
                bbox_wgs84=bbox_wgs84,
                progress_interval=progress_interval,
                verbose=verbose,
                io_sleep_ms=io_sleep_ms,
                warp_threads=warp_threads,
                overwrite=overwrite,
            )

            intermediate_mbtiles.append(intermediate_path)

            # Log memory after completing the group
            try:
                rss_after = get_rss_bytes()
                if verbose:
                    print(f"Memory after group {i+1}: {format_bytes(rss_after)}")
                    if rss_before is not None:
                        diff = rss_after - rss_before
                        print(f"Memory delta for group {i+1}: {format_bytes(diff)}")
            except Exception:
                pass

            group_elapsed = time.time() - group_start_time
            if verbose:
                print(f"\nGroup {i+1}/{len(groups)} completed in {group_elapsed/60:.1f} minutes")

        except Exception as e:
            print(f"\nError processing group {i+1}/{len(groups)} ({group.name}): {e}")
            print(f"To resume from this group, use: --resume-from {i}")
            raise

    # すべてのグループが完了したら、MBTilesをマージ
    if verbose:
        print(f"\n{'='*70}")
        print("Merging intermediate MBTiles files...")
        print(f"{'='*70}\n")

    merged_mbtiles = output_pmtiles.with_suffix(".mbtiles")

    try:
        merge_mbtiles_files(
            input_paths=intermediate_mbtiles,
            output_path=merged_mbtiles,
            verify_overlaps=True,
            overwrite=overwrite,
            verbose=verbose,
        )
    except Exception as e:
        print(f"\nError merging MBTiles: {e}")
        raise

    # PMTilesに変換
    if verbose:
        print(f"\n{'='*70}")
        print("Converting to PMTiles...")
        print(f"{'='*70}\n")

    try:
        pmtiles_exe = shutil.which("pmtiles") or shutil.which("pmtiles-cli")
        if pmtiles_exe:
            if verbose:
                print(f"Using: {pmtiles_exe}")
            subprocess.check_call(
                [pmtiles_exe, "convert", str(merged_mbtiles), str(output_pmtiles)]
            )
            if verbose:
                print(f"\nPMTiles created: {output_pmtiles}")
        else:
            # Python fallback
            try:
                from .mbtiles_to_pmtiles import mbtiles_to_pmtiles

                if verbose:
                    print("Using Python fallback for PMTiles conversion")
                mbtiles_to_pmtiles(merged_mbtiles, output_pmtiles)
                if verbose:
                    print(f"\nPMTiles created: {output_pmtiles}")
            except Exception:
                print(
                    "\nWarning: PMTiles conversion not available. "
                    f"MBTiles is available at: {merged_mbtiles}"
                )
    except Exception as e:
        print(f"\nWarning: PMTiles conversion failed: {e}")
        print(f"MBTiles is available at: {merged_mbtiles}")

    # 中間ファイルのクリーンアップ
    if not keep_intermediates:
        if verbose:
            print(f"\n{'='*70}")
            print("Cleaning up intermediate files...")
            print(f"{'='*70}\n")

        for intermediate_path in intermediate_mbtiles:
            try:
                if intermediate_path.exists():
                    intermediate_path.unlink()
                    if verbose:
                        print(f"Removed: {intermediate_path.name}")
            except Exception as e:
                print(f"Warning: Failed to remove {intermediate_path.name}: {e}")

    if verbose:
        print(f"\n{'='*70}")
        print("SPLIT AGGREGATE COMPLETED")
        print(f"{'='*70}")
        print(f"Output: {output_pmtiles}")
        if merged_mbtiles.exists():
            print(f"MBTiles: {merged_mbtiles}")
        print(f"{'='*70}\n")


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="Split aggregate: Process zoom levels in groups to reduce memory usage",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default="output/fusi.pmtiles",
        help="Output PMTiles path",
    )
    parser.add_argument(
        "--split-pattern",
        default="balanced",
        choices=["balanced", "safe", "fast", "incremental", "single"],
        help="Zoom split pattern to use",
    )
    parser.add_argument(
        "--resume-from",
        type=int,
        metavar="N",
        help="Resume from group N (0-based index)",
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Optional WGS84 bounding box",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=200,
        help="Tile interval for progress updates",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress verbose output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output (overrides --silent)",
    )
    parser.add_argument(
        "--io-sleep-ms",
        type=int,
        default=1,
        help="Sleep milliseconds per tile",
    )
    parser.add_argument(
        "--warp-threads",
        type=int,
        default=1,
        help="Number of warp threads",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="Keep intermediate MBTiles files after merging",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        help="Source names under source-store/",
    )

    args = parser.parse_args()

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

    bbox = tuple(args.bbox) if args.bbox else None

    try:
        run_split_aggregate(
            sources=args.sources,
            output_pmtiles=args.output,
            split_pattern=args.split_pattern,
            resume_from=args.resume_from,
            bbox_wgs84=bbox,
            progress_interval=args.progress_interval,
            verbose=args.verbose,
            io_sleep_ms=args.io_sleep_ms,
            warp_threads=args.warp_threads,
            overwrite=args.overwrite,
            keep_intermediates=args.keep_intermediates,
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        raise SystemExit(130)
    except Exception as e:
        print(f"\n\nError: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
