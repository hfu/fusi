#!/usr/bin/env python3
"""Generate z=6 subtree list from source-store bounds.csv files.

Reads `source-store/<source>/bounds.csv` files (CSV rows: filename,left,bottom,right,top,width,height)
and generates the set of z=6 tiles that cover all source footprints. Outputs
JSON and a simple CSV (tile_x,tile_y,source_count,examplesources...)

Usage:
    python scripts/generate_subtree_list.py --source-store source-store --out output/subtrees.json

Optional:
    --per-source    : also output per-source tile lists under output/subtrees_by_source/
    --z LEVEL       : use other z (default 6)

This tool is lightweight and relies on `mercantile` for tile math. If
`bounds.csv` is missing for a source, the source is skipped with a warning.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

try:
    import mercantile
except Exception:
    print("Error: mercantile is required. Install with: pip install mercantile")
    raise


def read_bounds_csv(path: Path) -> List[Tuple[float, float, float, float]]:
    rows = []
    if not path.exists():
        return rows
    with path.open('r', encoding='utf-8') as fh:
        rdr = csv.reader(fh)
        hdr = next(rdr, None)
        # Expect header: filename,left,bottom,right,top,width,height
        for r in rdr:
            if len(r) < 5:
                continue
            try:
                left = float(r[1]); bottom = float(r[2]); right = float(r[3]); top = float(r[4])
                rows.append((left, bottom, right, top))
            except Exception:
                continue
    return rows


def tiles_for_bounds(bbox: Tuple[float, float, float, float], z: int) -> Set[Tuple[int, int]]:
    west, south, east, north = bbox
    tiles = set()
    for t in mercantile.tiles(west, south, east, north, [z]):
        tiles.add((t.x, t.y))
    return tiles


def generate(source_store: Path, z: int = 6, per_source: bool = False):
    source_dirs = [p for p in source_store.iterdir() if p.is_dir()]
    all_tiles: Set[Tuple[int, int]] = set()
    tile_to_sources: Dict[Tuple[int, int], Set[str]] = defaultdict(set)
    per_source_tiles: Dict[str, Set[Tuple[int, int]]] = {}

    for sdir in sorted(source_dirs):
        bounds_csv = sdir / 'bounds.csv'
        source_name = sdir.name
        bboxes = read_bounds_csv(bounds_csv)
        if not bboxes:
            print(f"[warn] no bounds.csv or empty for source: {source_name} (skipping)")
            continue
        stiles: Set[Tuple[int, int]] = set()
        for bbox in bboxes:
            tset = tiles_for_bounds(bbox, z)
            stiles.update(tset)
        per_source_tiles[source_name] = stiles
        for t in stiles:
            tile_to_sources[t].add(source_name)
        all_tiles.update(stiles)
        print(f"[info] source={source_name} tiles={len(stiles)}")

    # Build output structures
    tile_list = []
    for (x, y) in sorted(all_tiles):
        sources = sorted(tile_to_sources.get((x, y), []))
        tile_list.append({
            'x': x,
            'y': y,
            'z': z,
            'source_count': len(sources),
            'sources': sources[:5],
        })

    return tile_list, per_source_tiles


def write_outputs(tile_list, per_source_tiles, out_path: Path, per_source_dir: Path | None = None):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as fh:
        json.dump(tile_list, fh, indent=2, ensure_ascii=False)
    csvp = out_path.with_suffix('.csv')
    with csvp.open('w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['x', 'y', 'z', 'source_count', 'sources'])
        for t in tile_list:
            w.writerow([t['x'], t['y'], t['z'], t['source_count'], ';'.join(t['sources'])])

    if per_source_dir:
        per_source_dir.mkdir(parents=True, exist_ok=True)
        for src, tiles in per_source_tiles.items():
            p = per_source_dir / f"{src}_z{tile_list[0]['z']}.txt"
            with p.open('w', encoding='utf-8') as fh:
                for x, y in sorted(tiles):
                    fh.write(f"{x},{y}\n")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--source-store', default='source-store', help='Path to source-store')
    p.add_argument('--z', type=int, default=6, help='Zoom level for subtree tiling (default 6)')
    p.add_argument('--per-source', action='store_true', help='Also write per-source tile lists')
    p.add_argument('--out', default='output/subtrees.json', help='Output JSON path')
    args = p.parse_args(argv)

    source_store = Path(args.source_store)
    if not source_store.exists():
        print(f"Error: source-store not found at {source_store}")
        return 2

    tile_list, per_source_tiles = generate(source_store, z=args.z, per_source=args.per_source)
    write_outputs(tile_list, per_source_tiles, Path(args.out), Path(args.out).parent / 'subtrees_by_source' if args.per_source else None)
    print(f"Wrote {len(tile_list)} tiles to {args.out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
