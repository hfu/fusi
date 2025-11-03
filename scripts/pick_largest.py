#!/usr/bin/env python3
"""Pick the largest .tif file under a directory and print its path.

Usage: python scripts/pick_largest.py <input_dir>
"""
import sys
from pathlib import Path


def find_largest_tif(directory: Path):
    if not directory.exists() or not directory.is_dir():
        return None
    tifs = list(directory.glob('*.tif'))
    if not tifs:
        return None
    # Use file size in bytes
    largest = max(tifs, key=lambda p: p.stat().st_size)
    return largest


def main():
    if len(sys.argv) < 2:
        print("Usage: pick_largest.py <input_dir>", file=sys.stderr)
        sys.exit(2)
    input_dir = Path(sys.argv[1])
    largest = find_largest_tif(input_dir)
    if largest is None:
        print("No .tif files found", file=sys.stderr)
        sys.exit(1)
    print(str(largest))


if __name__ == '__main__':
    main()
