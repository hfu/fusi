#!/usr/bin/env python3
"""Thin wrapper script to generate a single lineage tile using pipelines.lineage.

Usage (example):
  python3 scripts/generate_lineage_tile.py --z 8 --x 220 --y 152 --sources dem1a dem10b --out output/lineage_z8_x220_y152.png
"""
import sys
from pathlib import Path

# Ensure repo root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipelines.lineage import main


if __name__ == "__main__":
    raise SystemExit(main())
