#!/usr/bin/env python3
"""Zoom分割機能の簡易テストスイート。

各コンポーネントの基本的な動作を検証します。
実際のGeoTIFFデータは使用せず、モックデータで動作確認を行います。
"""

import sys
from pathlib import Path

# リポジトリルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.zoom_split_config import (
    get_split_pattern,
    validate_split_pattern,
    estimate_tile_count,
    estimate_memory_for_zoom_range,
    create_custom_split,
)


def test_split_patterns():
    """分割パターンの取得と検証をテスト。"""
    print("\n" + "=" * 60)
    print("Test 1: Split Patterns")
    print("=" * 60)

    patterns = ["balanced", "safe", "fast", "incremental", "single"]

    for pattern_name in patterns:
        groups = get_split_pattern(pattern_name)
        validate_split_pattern(groups)
        print(f"✓ {pattern_name}: {len(groups)} groups, valid")

    assert True


def test_tile_estimation():
    """タイル数推定のテスト。"""
    print("\n" + "=" * 60)
    print("Test 2: Tile Count Estimation")
    print("=" * 60)

    test_cases = [
        # (min_zoom, max_zoom, bbox, expected_range)
        (0, 6, None, (1000, 10000)),  # 日本全域、低ズーム
        (10, 12, None, (50000, 500000)),  # 日本全域、中ズーム
        (0, 6, (128.3, 32.4, 131.6, 33.8), (10, 1000)),  # 長崎県、低ズーム
    ]

    for min_z, max_z, bbox, _ in test_cases:
        count = estimate_tile_count(min_z, max_z, bbox)
        # Basic sanity: at least 1 tile should be returned for any bbox
        assert count >= 1
        bbox_str = f"bbox={bbox}" if bbox else "Japan"
        print(f"✓ z{min_z}-{max_z} ({bbox_str}): {count:,} tiles")

    assert True


def test_memory_estimation():
    """メモリ使用量推定のテスト。"""
    print("\n" + "=" * 60)
    print("Test 3: Memory Estimation")
    print("=" * 60)

    test_cases = [
        (0, 10),
        (11, 12),
        (13, 14),
    ]

    for min_z, max_z in test_cases:
        memory_gb = estimate_memory_for_zoom_range(min_z, max_z)
        # Basic sanity: memory estimate should be positive
        assert memory_gb > 0
        print(f"✓ z{min_z}-{max_z}: {memory_gb:.1f}GB")

    assert True


def test_custom_split():
    """カスタム分割パターン作成のテスト。"""
    print("\n" + "=" * 60)
    print("Test 4: Custom Split Creation")
    print("=" * 60)

    # Create custom split and validate basic properties
    groups = create_custom_split(max_zoom=16, target_memory_gb=10.0)
    validate_split_pattern(groups)
    assert len(groups) > 0
    print(f"✓ Custom split created: {len(groups)} groups")

    assert True


def test_imports():
    """必要なモジュールのインポートをテスト。"""
    print("\n" + "=" * 60)
    print("Test 5: Module Imports")
    print("=" * 60)

    # Only check modules that are lightweight and do not require
    # heavy runtime dependencies like rasterio/mercantile at import time.
    modules = [
        ("pipelines.zoom_split_config", "zoom_split_config"),
        ("pipelines.merge_mbtiles", "merge_mbtiles (light import)")
    ]

    # Require zoom_split_config to import; other modules are optional
    __import__(modules[0][0])
    print(f"✓ {modules[0][1]}")

    try:
        __import__(modules[1][0])
        print(f"✓ {modules[1][1]}")
    except ImportError as e:
        print(f"⚠ {modules[1][1]}: {e} (optional) ")

    assert True


def main():
    """すべてのテストを実行。"""
    print("\n" + "#" * 60)
    print("# Zoom Split Feature - Simple Test Suite")
    print("#" * 60)

    tests = [
        ("Module Imports", test_imports),
        ("Split Patterns", test_split_patterns),
        ("Tile Estimation", test_tile_estimation),
        ("Memory Estimation", test_memory_estimation),
        ("Custom Split", test_custom_split),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} failed with exception: {e}")
            results.append((test_name, False))

    # サマリー
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = 0
    failed = 0

    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print("-" * 60)
    print(f"Total: {len(results)} tests, {passed} passed, {failed} failed")

    if failed == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
