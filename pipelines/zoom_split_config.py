#!/usr/bin/env python3
"""Zoom分割の設定を管理するモジュール。

メモリ使用量を抑えるために、ズームレベルを複数のグループに分割して
処理する際の設定を提供します。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class ZoomGroup:
    """ズームレベルのグループを表すデータクラス。"""

    min_zoom: int
    max_zoom: int
    estimated_tiles: int  # 日本全域での推定タイル数
    estimated_memory_gb: float  # 推定メモリ使用量（GB）

    @property
    def name(self) -> str:
        """グループ名を返す（例: "z0-10"）。"""
        if self.min_zoom == self.max_zoom:
            return f"z{self.min_zoom}"
        return f"z{self.min_zoom}-{self.max_zoom}"

    @property
    def zoom_range(self) -> range:
        """ズームレベルの範囲をrangeオブジェクトで返す。"""
        return range(self.min_zoom, self.max_zoom + 1)

    def __str__(self) -> str:
        return (
            f"{self.name}: ~{self.estimated_tiles:,} tiles, "
            f"~{self.estimated_memory_gb:.1f}GB memory"
        )


# 分割パターンの定義

SPLIT_PATTERNS = {
    "single": [
        # 分割なし（テスト用、小規模データ向け）
        ZoomGroup(0, 16, 20_000_000, 40.0),
    ],
    "balanced": [
        # 推奨: 4分割パターン（バランス重視）
        ZoomGroup(0, 10, 55_000, 6.0),
        ZoomGroup(11, 12, 200_000, 8.0),
        ZoomGroup(13, 14, 1_000_000, 10.0),
        ZoomGroup(15, 16, 20_000_000, 10.0),
    ],
    "safe": [
        # 安全重視: 6分割パターン（メモリを確実に抑える）
        ZoomGroup(0, 9, 14_000, 5.0),
        ZoomGroup(10, 11, 90_000, 6.0),
        ZoomGroup(12, 12, 130_000, 7.0),
        ZoomGroup(13, 13, 500_000, 8.0),
        ZoomGroup(14, 14, 2_000_000, 9.0),
        ZoomGroup(15, 16, 20_000_000, 10.0),
    ],
    "fast": [
        # 速度重視: 3分割パターン（高速ストレージ向け）
        ZoomGroup(0, 11, 250_000, 8.0),
        ZoomGroup(12, 13, 1_500_000, 12.0),
        ZoomGroup(14, 16, 22_000_000, 12.0),
    ],
    "incremental": [
        # 段階的: 各ズームを個別処理（デバッグ・検証用）
        ZoomGroup(0, 6, 5_000, 3.0),
        ZoomGroup(7, 9, 9_000, 4.0),
        ZoomGroup(10, 10, 40_000, 5.0),
        ZoomGroup(11, 11, 80_000, 6.0),
        ZoomGroup(12, 12, 130_000, 7.0),
        ZoomGroup(13, 13, 500_000, 8.0),
        ZoomGroup(14, 14, 2_000_000, 9.0),
        ZoomGroup(15, 15, 8_000_000, 10.0),
        ZoomGroup(16, 16, 12_000_000, 10.0),
    ],
}


def get_split_pattern(pattern: str = "balanced") -> List[ZoomGroup]:
    """指定された分割パターンを返す。

    Args:
        pattern: 分割パターン名（"balanced", "safe", "fast", "incremental", "single"）

    Returns:
        ZoomGroupのリスト

    Raises:
        ValueError: 不正なパターン名が指定された場合
    """
    if pattern not in SPLIT_PATTERNS:
        available = ", ".join(SPLIT_PATTERNS.keys())
        raise ValueError(
            f"Unknown split pattern: {pattern}. Available patterns: {available}"
        )

    return SPLIT_PATTERNS[pattern]


def estimate_tile_count(min_zoom: int, max_zoom: int, bbox_wgs84: Optional[Tuple[float, float, float, float]] = None) -> int:
    """指定されたズーム範囲のタイル数を推定する。

    Args:
        min_zoom: 最小ズームレベル
        max_zoom: 最大ズームレベル
        bbox_wgs84: WGS84のバウンディングボックス (west, south, east, north)
                    Noneの場合は日本全域を仮定

    Returns:
        推定タイル数
    """
    # 日本全域の概算bbox（度）
    japan_bbox = (122.0, 24.0, 154.0, 46.0)
    bbox = bbox_wgs84 if bbox_wgs84 is not None else japan_bbox

    west, south, east, north = bbox

    total_tiles = 0
    for z in range(min_zoom, max_zoom + 1):
        # Web Mercator投影でのタイル数を計算
        # 経度方向のタイル数（少数切り上げで少なくとも1）
        tiles_x = max(1, math.ceil((east - west) / 360.0 * (2 ** z)))

        # 緯度方向のタイル数（Web Mercatorの変換）
        lat_rad_min = math.radians(south)
        lat_rad_max = math.radians(north)
        y_min = (1 - math.log(math.tan(lat_rad_max) + 1 / math.cos(lat_rad_max)) / math.pi) / 2 * (2 ** z)
        y_max = (1 - math.log(math.tan(lat_rad_min) + 1 / math.cos(lat_rad_min)) / math.pi) / 2 * (2 ** z)
        tiles_y = max(1, math.ceil(abs(y_max - y_min)))

        total_tiles += tiles_x * tiles_y

    # Ensure at least one tile is reported for tiny bbox ranges
    return max(1, total_tiles)


def estimate_memory_for_zoom_range(
    min_zoom: int,
    max_zoom: int,
    bbox_wgs84: Optional[Tuple[float, float, float, float]] = None,
    base_memory_gb: float = 4.0,
    memory_per_million_tiles_gb: float = 2.0,
) -> float:
    """指定されたズーム範囲のメモリ使用量を推定する。

    Args:
        min_zoom: 最小ズームレベル
        max_zoom: 最大ズームレベル
        bbox_wgs84: WGS84のバウンディングボックス
        base_memory_gb: 基本メモリ使用量（Python、GDAL等）
        memory_per_million_tiles_gb: 100万タイルあたりの追加メモリ（GB）

    Returns:
        推定メモリ使用量（GB）
    """
    tile_count = estimate_tile_count(min_zoom, max_zoom, bbox_wgs84)
    tile_memory = (tile_count / 1_000_000.0) * memory_per_million_tiles_gb
    return base_memory_gb + tile_memory


def create_custom_split(
    max_zoom: int,
    target_memory_gb: float = 10.0,
    bbox_wgs84: Optional[Tuple[float, float, float, float]] = None,
) -> List[ZoomGroup]:
    """目標メモリ使用量に基づいてカスタムの分割パターンを作成する。

    Args:
        max_zoom: 最大ズームレベル
        target_memory_gb: 各グループの目標メモリ使用量（GB）
        bbox_wgs84: WGS84のバウンディングボックス

    Returns:
        ZoomGroupのリスト
    """
    groups: List[ZoomGroup] = []
    current_min = 0

    for z in range(max_zoom + 1):
        # 現在のズームまでのメモリ使用量を推定
        estimated_memory = estimate_memory_for_zoom_range(current_min, z, bbox_wgs84)

        if estimated_memory >= target_memory_gb or z == max_zoom:
            # グループを確定
            tile_count = estimate_tile_count(current_min, z, bbox_wgs84)
            group = ZoomGroup(
                min_zoom=current_min,
                max_zoom=z,
                estimated_tiles=tile_count,
                estimated_memory_gb=estimated_memory,
            )
            groups.append(group)
            current_min = z + 1

    return groups


def validate_split_pattern(groups: List[ZoomGroup], max_zoom: int = 16) -> None:
    """分割パターンの妥当性を検証する。

    Args:
        groups: 検証するZoomGroupのリスト
        max_zoom: 期待される最大ズームレベル

    Raises:
        ValueError: パターンに問題がある場合
    """
    if not groups:
        raise ValueError("Split pattern is empty")

    # ズームレベルの連続性を確認
    expected_next = 0
    for i, group in enumerate(groups):
        if group.min_zoom != expected_next:
            raise ValueError(
                f"Gap in zoom levels: group {i} starts at z{group.min_zoom}, "
                f"expected z{expected_next}"
            )
        if group.min_zoom > group.max_zoom:
            raise ValueError(
                f"Invalid zoom range in group {i}: "
                f"min_zoom ({group.min_zoom}) > max_zoom ({group.max_zoom})"
            )
        expected_next = group.max_zoom + 1

    # 最大ズームレベルを確認
    if groups[-1].max_zoom != max_zoom:
        raise ValueError(
            f"Split pattern does not cover all zooms: "
            f"last group ends at z{groups[-1].max_zoom}, expected z{max_zoom}"
        )


def print_split_summary(groups: List[ZoomGroup]) -> None:
    """分割パターンのサマリーを表示する。"""
    print(f"\nSplit pattern: {len(groups)} groups")
    print("-" * 60)

    total_tiles = 0
    max_memory = 0.0

    for i, group in enumerate(groups, start=1):
        print(f"Group {i}: {group}")
        total_tiles += group.estimated_tiles
        max_memory = max(max_memory, group.estimated_memory_gb)

    print("-" * 60)
    print(f"Total estimated tiles: {total_tiles:,}")
    print(f"Peak memory usage: ~{max_memory:.1f}GB")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Display zoom split patterns and memory estimates"
    )
    parser.add_argument(
        "--pattern",
        default="balanced",
        choices=list(SPLIT_PATTERNS.keys()),
        help="Split pattern to display",
    )
    parser.add_argument(
        "--custom",
        action="store_true",
        help="Create custom split pattern based on target memory",
    )
    parser.add_argument(
        "--target-memory",
        type=float,
        default=10.0,
        help="Target memory per group (GB) for custom split",
    )
    parser.add_argument(
        "--max-zoom", type=int, default=16, help="Maximum zoom level"
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Bounding box for tile count estimation",
    )

    args = parser.parse_args()

    bbox = tuple(args.bbox) if args.bbox else None

    if args.custom:
        print(f"\nCreating custom split pattern (target: {args.target_memory}GB per group):")
        groups = create_custom_split(args.max_zoom, args.target_memory, bbox)
    else:
        groups = get_split_pattern(args.pattern)
        print(f"\nSplit pattern: {args.pattern}")

    try:
        validate_split_pattern(groups, args.max_zoom)
        print_split_summary(groups)
    except ValueError as e:
        print(f"Error: {e}")
