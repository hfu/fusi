#!/usr/bin/env python3
"""Aggregate multiple GeoTIFF tiles into a single Terrarium PMTiles archive.

This script follows the mapterhorn approach by using bounds.csv to locate
input rasters, selecting only the files that intersect the requested spatial
coverage, and mosaicking them on the fly for each output Web Mercator tile.

Usage:
    python pipelines/aggregate_pmtiles.py <source_name> <output_pmtiles>
        [--min-zoom MIN] [--max-zoom MAX]
        [--bbox WEST SOUTH EAST NORTH]

Examples:
    # Merge the entire source-store/japan_dem directory into one PMTiles
    python pipelines/aggregate_pmtiles.py japan_dem output/japan.pmtiles

    # Export only the specified lat/lon bounding box
    python pipelines/aggregate_pmtiles.py japan_dem output/hokkaido.pmtiles \
        --bbox 139.0 41.0 146.0 46.0 --min-zoom 6 --max-zoom 14
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Sequence, Tuple
import time

import mercantile
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.warp import transform_bounds, reproject

import imagecodecs

try:  # Allow running as a module or script
    from .convert_terrarium import encode_terrarium
    from .mbtiles_writer import create_mbtiles_from_tiles
except ImportError:  # pragma: no cover - fallback for direct execution
    from convert_terrarium import encode_terrarium
    from mbtiles_writer import create_mbtiles_from_tiles

EPSG_4326 = "EPSG:4326"
EPSG_3857 = "EPSG:3857"

EARTH_CIRCUMFERENCE_M = 40075016.68557849
REFERENCE_TILE_SIZE = 512
BASE_RESOLUTION_M = EARTH_CIRCUMFERENCE_M / REFERENCE_TILE_SIZE
MAX_SUPPORTED_ZOOM = 17


@dataclass(frozen=True)
class SourceRecord:
    """Metadata for a single GeoTIFF derived from bounds.csv."""

    path: Path
    left: float
    bottom: float
    right: float
    top: float
    width: int
    height: int
    pixel_size: float
    source: str
    priority: int

    @property
    def bounds_mercator(self) -> Tuple[float, float, float, float]:
        return self.left, self.bottom, self.right, self.top


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate GeoTIFFs into a Terrarium tiles archive (MBTiles + PMTiles)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output/fusi.pmtiles",
        help="Output PMTiles path (MBTilesは同名で拡張子だけ .mbtiles に変更)",
    )
    parser.add_argument("--min-zoom", type=int, default=0, help="Minimum zoom level")
    parser.add_argument(
        "--max-zoom",
        type=int,
        default=None,
        help="Maximum zoom level (defaults to auto based on source resolution)",
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
        "--verbose",
        action="store_true",
        help="Increase logging verbosity during aggregation",
    )
    parser.add_argument(
        "--io-sleep-ms",
        type=int,
        default=1,
        help="Sleep for the given milliseconds per emitted tile to ease I/O pressure",
    )
    parser.add_argument(
        "--fsync-interval-tiles",
        type=int,
        default=10000,
        help="Flush+fsync spool file every N tiles (0 disables)",
    )
    parser.add_argument(
        "--warp-threads",
        type=int,
        default=1,
        help="Number of threads for raster warping (reproject). Use 1 to reduce I/O pressure",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        help="One or more source names under source-store/ (priority order)",
    )
    args = parser.parse_args()

    if args.min_zoom < 0 or (args.max_zoom is not None and args.max_zoom < 0):
        parser.error("Zoom levels must be non-negative")
    if args.max_zoom is not None and args.min_zoom > args.max_zoom:
        parser.error("min_zoom cannot be larger than max_zoom")

    return args


def recommended_max_zoom(pixel_size_m: float) -> int:
    if not math.isfinite(pixel_size_m) or pixel_size_m <= 0:
        return MAX_SUPPORTED_ZOOM
    zoom = math.ceil(math.log2(BASE_RESOLUTION_M / pixel_size_m))
    return max(0, min(MAX_SUPPORTED_ZOOM, zoom))


def load_bounds(source_name: str, priority: int = 0) -> List[SourceRecord]:
    bounds_path = Path("source-store") / source_name / "bounds.csv"
    if not bounds_path.exists():
        raise FileNotFoundError(
            f"Bounds file not found: {bounds_path}. Run 'just bounds {source_name}' first."
        )

    records: List[SourceRecord] = []

    with bounds_path.open() as fp:
        reader = csv.DictReader(fp)
        required = {"filename", "left", "bottom", "right", "top", "width", "height"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"bounds.csv is missing columns: {sorted(missing)}")

        for row in reader:
            tif_path = bounds_path.parent / row["filename"]
            if not tif_path.exists():
                print(f"Warning: Skipping missing file {tif_path}")
                continue

            width = int(row["width"])
            height = int(row["height"])
            left = float(row["left"])
            bottom = float(row["bottom"])
            right = float(row["right"])
            top = float(row["top"])

            if not (math.isfinite(left) and math.isfinite(bottom) and math.isfinite(right) and math.isfinite(top)):
                print(f"Warning: Skipping invalid bounds for {tif_path}")
                continue

            span_x = max(abs(right - left), 1e-6)
            span_y = max(abs(top - bottom), 1e-6)
            res_x = span_x / max(width, 1)
            res_y = span_y / max(height, 1)
            pixel_size = max(res_x, res_y)

            records.append(
                SourceRecord(
                    path=tif_path,
                    left=left,
                    bottom=bottom,
                    right=right,
                    top=top,
                    width=width,
                    height=height,
                    pixel_size=pixel_size,
                    source=source_name,
                    priority=priority,
                )
            )

    if not records:
        raise RuntimeError(f"No valid GeoTIFF entries available for source '{source_name}'")

    return records


def union_bounds(records: Sequence[SourceRecord]) -> Tuple[float, float, float, float]:
    left = min(r.left for r in records)
    bottom = min(r.bottom for r in records)
    right = max(r.right for r in records)
    top = max(r.top for r in records)
    return left, bottom, right, top


def intersects(bounds_a: Tuple[float, float, float, float], bounds_b: Tuple[float, float, float, float]) -> bool:
    a_left, a_bottom, a_right, a_top = bounds_a
    b_left, b_bottom, b_right, b_top = bounds_b
    return not (a_right <= b_left or a_left >= b_right or a_top <= b_bottom or a_bottom >= b_top)


def read_tile_from_source(
    record: SourceRecord,
    tile_bounds_mercator: mercantile.TileBoundingBox,
    out_shape: Tuple[int, int],
    warp_threads: int,
) -> Optional[np.ndarray]:
    """Reproject the raster onto the requested tile grid and return float32 elevations."""

    height, width = out_shape
    tile_transform = transform_from_bounds(
        tile_bounds_mercator.left,
        tile_bounds_mercator.bottom,
        tile_bounds_mercator.right,
        tile_bounds_mercator.top,
        width,
        height,
    )

    with rasterio.open(record.path) as src:
        if src.crs is None:
            raise ValueError(f"CRS not defined for {record.path}")

        destination = np.full(out_shape, np.nan, dtype=np.float32)

        # Build explicit source mask to ensure NODATA propagates as NaN
        try:
            src_arr = src.read(1, masked=False).astype("float32")
        except Exception as exc:
            raise ValueError(f"Failed to read band from {record.path}: {exc}")

        if src.nodata is not None:
            valid_mask = src_arr != src.nodata
            src_arr[~valid_mask] = np.nan
        else:
            # Use alpha/mask band if available
            try:
                valid_mask = src.read_masks(1) != 0
            except Exception:
                # Fallback: treat all as valid; outside bounds will still be NaN after reproject
                valid_mask = np.ones_like(src_arr, dtype=bool)

        reproject(
            source=src_arr,
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=tile_transform,
            dst_crs=EPSG_3857,
            resampling=Resampling.bilinear,
            source_mask=valid_mask.astype("uint8"),
            dst_nodata=np.nan,
            num_threads=max(1, int(warp_threads)),
        )

        if np.isnan(destination).all():
            return None

        return destination


def merge_tile_candidates(candidates: Iterable[np.ndarray]) -> Optional[np.ndarray]:
    merged: Optional[np.ndarray] = None

    for data in candidates:
        if data is None:
            continue

        if merged is None:
            merged = data
            continue

        mask = np.isnan(merged) & ~np.isnan(data)
        if np.any(mask):
            merged = np.where(mask, data, merged)

    return merged


def generate_aggregated_tiles(
    records: Sequence[SourceRecord],
    min_zoom: int,
    max_zoom: int,
    bbox_wgs84: Optional[Tuple[float, float, float, float]] = None,
    progress_interval: int = 500,
    verbose: bool = False,
    io_sleep_ms: int = 0,
    warp_threads: int = 1,
) -> Generator[Tuple[int, int, int, bytes], None, None]:
    # Track start time for ETA calculations and timestamped verbose logs
    start_time = time.time()

    print("[phase] Computing union bounds...")
    union_left, union_bottom, union_right, union_top = union_bounds(records)
    union_west, union_south, union_east, union_north = transform_bounds(
        EPSG_3857,
        EPSG_4326,
        union_left,
        union_bottom,
        union_right,
        union_top,
        densify_pts=21,
    )

    if bbox_wgs84 is not None:
        west, south, east, north = bbox_wgs84
        west = max(west, union_west)
        south = max(south, union_south)
        east = min(east, union_east)
        north = min(north, union_north)
        if west >= east or south >= north:
            raise ValueError("Requested bbox does not overlap source coverage")
    else:
        west, south, east, north = union_west, union_south, union_east, union_north

    # Build spatial index keyed by zoom level 5 tiles for efficient candidate filtering
    if verbose:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [phase] Building coarse buckets (z5) for source records...")
    else:
        print("[phase] Building coarse buckets (z5) for source records...")
    buckets: Dict[Tuple[int, int, int], List[SourceRecord]] = defaultdict(list)
    coarse_zoom = 5
    for record in records:
        west_r, south_r, east_r, north_r = transform_bounds(
            EPSG_3857,
            EPSG_4326,
            record.left,
            record.bottom,
            record.right,
            record.top,
            densify_pts=5,
        )
        for tile in mercantile.tiles(west_r, south_r, east_r, north_r, coarse_zoom):
            buckets[(coarse_zoom, tile.x, tile.y)].append(record)

    if verbose:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [phase] Coarse buckets ready: {len(buckets)} tiles with candidates")
    else:
        print(f"[phase] Coarse buckets ready: {len(buckets)} tiles with candidates")

    per_zoom_candidate_counts: Dict[int, int] = {}
    total_candidates = 0
    if verbose:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [phase] Scanning candidate tile counts per zoom...")
    else:
        print("[phase] Scanning candidate tile counts per zoom...")
    for z in range(min_zoom, max_zoom + 1):
        count = sum(1 for _ in mercantile.tiles(west, south, east, north, z))
        per_zoom_candidate_counts[z] = count
        total_candidates += count

    if verbose:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Planned tile scan: {total_candidates} candidates across zooms {min_zoom}-{max_zoom}")
    else:
        print(
            f"Planned tile scan: {total_candidates} candidates across zooms {min_zoom}-{max_zoom}"
        )
    if total_candidates:
        detail = ", ".join(
            f"z{z}:{per_zoom_candidate_counts[z]}" for z in range(min_zoom, max_zoom + 1)
        )
        if verbose:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]   Per-zoom candidate counts: {detail}")
        else:
            print(f"  Per-zoom candidate counts: {detail}")

    checked_tiles = 0
    emitted_tiles = 0

    for z in range(min_zoom, max_zoom + 1):
        if verbose:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [z{z}] Starting tile scan...")
        else:
            print(f"[z{z}] Starting tile scan...")
        for tile in mercantile.tiles(west, south, east, north, z):
            checked_tiles += 1
            xy_bounds = mercantile.xy_bounds(tile)
            shift = max(z - coarse_zoom, 0)
            bucket_key = (coarse_zoom, tile.x >> shift, tile.y >> shift)
            candidate_records = buckets.get(bucket_key, [])
            if not candidate_records:
                continue

            # Filter candidates precisely using Mercator bounds
            overlapping = [
                record for record in candidate_records
                if intersects(record.bounds_mercator, (xy_bounds.left, xy_bounds.bottom, xy_bounds.right, xy_bounds.top))
            ]
            if not overlapping:
                continue

            # Sort by source priority first (lower = higher priority), then finer pixel size
            overlapping.sort(key=lambda r: (r.priority, r.pixel_size))
            tile_arrays: List[np.ndarray] = []
            for rec in overlapping:
                try:
                    data = read_tile_from_source(rec, xy_bounds, out_shape=(512, 512), warp_threads=warp_threads)
                except Exception as exc:  # pragma: no cover - defensive logging
                    print(f"Warning: {exc}")
                    continue
                if data is not None:
                    tile_arrays.append(data)

            merged = merge_tile_candidates(tile_arrays)
            if merged is None or np.isnan(merged).all():
                continue

            try:
                rgb = encode_terrarium(merged, z)
                webp = imagecodecs.webp_encode(rgb, lossless=True)
            except Exception as exc:  # pragma: no cover - defensive logging
                print(f"Warning: Failed to encode tile {z}/{tile.x}/{tile.y}: {exc}")
                continue

            emitted_tiles += 1
            if progress_interval and (
                emitted_tiles % progress_interval == 0 or checked_tiles == total_candidates
            ):
                percent = (checked_tiles / total_candidates * 100.0) if total_candidates else 0.0
                # ETA based on checked_tiles processing rate
                now = time.time()
                elapsed = max(1e-6, now - start_time)
                rate = checked_tiles / elapsed if elapsed > 0 else 0
                eta_str = "?"
                if rate > 0 and total_candidates and checked_tiles < total_candidates:
                    remaining = total_candidates - checked_tiles
                    eta_seconds = int(remaining / rate)
                    eta_time = time.localtime(now + eta_seconds)
                    eta_str = time.strftime('%Y-%m-%d %H:%M:%S', eta_time) + f" (in {eta_seconds}s)"

                print(
                    f"Progress: {emitted_tiles} tiles written; processed {checked_tiles}/"
                    f"{total_candidates} candidates ({percent:.1f}%) ETA: {eta_str}"
                )

            yield z, tile.x, tile.y, webp

            if io_sleep_ms > 0:
                time.sleep(io_sleep_ms / 1000.0)

    print(
        f"Finished tile generation: {emitted_tiles} tiles produced from {checked_tiles} candidates"
    )


def main() -> None:
    args = parse_args()
    if not args.sources:
        raise SystemExit("At least one source name is required")

    # Load bounds for all sources with priority by order
    records: List[SourceRecord] = []
    for prio, src_name in enumerate(args.sources):
        recs = load_bounds(src_name, priority=prio)
        records.extend(recs)
        print(f"Loaded metadata for {len(recs)} GeoTIFF files from '{src_name}' (priority {prio})")

    finest_pixel_size = min(r.pixel_size for r in records)
    auto_max_zoom = recommended_max_zoom(finest_pixel_size)
    max_zoom = args.max_zoom if args.max_zoom is not None else auto_max_zoom
    if max_zoom > MAX_SUPPORTED_ZOOM:
        raise ValueError(f"Requested max_zoom {max_zoom} exceeds supported maximum {MAX_SUPPORTED_ZOOM}")
    if max_zoom < args.min_zoom:
        raise ValueError("Computed max_zoom is smaller than min_zoom; adjust inputs")

    if args.max_zoom is None:
        print(
            f"Auto-selected max zoom {max_zoom} for source GSD ≈ {finest_pixel_size:.2f} m (tile size {REFERENCE_TILE_SIZE}px)"
        )
    else:
        print(f"Using max zoom {max_zoom} (user-specified)")

    bbox = tuple(args.bbox) if args.bbox else None

    # 出力の設計:
    #   - ユーザは最終PMTilesパス（例: output/fusi.pmtiles）を指定
    #   - Python側では同じベース名で .mbtiles に差し替えたものを
    #     MBTiles の実ファイルとして使う
    pmtiles_path = Path(args.output)
    mbtiles_path = pmtiles_path.with_suffix(".mbtiles")
    mbtiles_path.parent.mkdir(parents=True, exist_ok=True)

    tiles = generate_aggregated_tiles(
        records=records,
        min_zoom=args.min_zoom,
        max_zoom=max_zoom,
        bbox_wgs84=bbox,
        progress_interval=args.progress_interval,
        verbose=args.verbose,
        io_sleep_ms=args.io_sleep_ms,
        warp_threads=args.warp_threads,
    )

    # For now we ignore fsync_interval_tiles here, because SQLite already
    # handles durability, and we favor throughput on the external SSD.
    print(f"Writing Terrarium WebP tiles into MBTiles: {mbtiles_path}")
    create_mbtiles_from_tiles(tiles, mbtiles_path)

    # PMTiles 変換は justfile 側で pmtiles CLI を用いて行う前提とする。
    print(f"MBTiles ready: {mbtiles_path} (intended PMTiles: {pmtiles_path})")


if __name__ == "__main__":
    main()
