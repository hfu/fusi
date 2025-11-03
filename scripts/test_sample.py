#!/usr/bin/env python3
"""Run a test conversion using the largest .tif in the input directory.

This script is intended to be executed under the project's pipenv Python:
  pipenv run python scripts/test_sample.py --input input --output output/sample.pmtiles
"""
import argparse
import subprocess
from pathlib import Path
import sys


def find_largest_tif(directory: Path):
    if not directory.exists() or not directory.is_dir():
        return None
    tifs = list(directory.glob('*.tif'))
    if not tifs:
        return None
    return max(tifs, key=lambda p: p.stat().st_size)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='input')
    p.add_argument('--output', default='docs/sample.pmtiles')
    args = p.parse_args()

    input_dir = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    largest = find_largest_tif(input_dir)
    if largest is None:
        print('No .tif files found in', input_dir, file=sys.stderr)
        sys.exit(1)

    print('Selected sample:', largest)

    cmd = [sys.executable, 'convert.py', str(largest), str(out_path)]
    print('Running:', ' '.join(cmd))
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print('convert.py failed', file=sys.stderr)
        sys.exit(res.returncode)


if __name__ == '__main__':
    main()
