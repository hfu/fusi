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

import imagecodecs
import mercantile
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.warp import transform_bounds, reproject

try:  # Allow running as a module or script
    from .convert_terrarium import create_pmtiles, encode_terrarium
except ImportError:  # pragma: no cover - fallback for direct execution
    from convert_terrarium import create_pmtiles, encode_terrarium

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

    @property
    def bounds_mercator(self) -> Tuple[float, float, float, float]:
        return self.left, self.bottom, self.right, self.top


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate GeoTIFFs into a Terrarium PMTiles archive",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("source_name", help="Name of the source directory under source-store/")
    parser.add_argument("output", help="Output PMTiles path")
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
        default=500,
        help="Tile interval for printing progress updates",
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


def load_bounds(source_name: str) -> List[SourceRecord]:
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

        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=tile_transform,
            dst_crs=EPSG_3857,
            resampling=Resampling.bilinear,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
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
) -> Generator[Tuple[int, int, int, bytes], None, None]:
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

    total_tiles = 0
    emitted_tiles = 0

    for z in range(min_zoom, max_zoom + 1):
        for tile in mercantile.tiles(west, south, east, north, z):
            total_tiles += 1
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

            overlapping.sort(key=lambda r: r.pixel_size)
            tile_arrays: List[np.ndarray] = []
            for rec in overlapping:
                try:
                    data = read_tile_from_source(rec, xy_bounds, out_shape=(512, 512))
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
            if progress_interval and emitted_tiles % progress_interval == 0:
                print(f"Generated {emitted_tiles} tiles (checked {total_tiles})")

            yield z, tile.x, tile.y, webp

    print(f"Finished tile generation: {emitted_tiles} tiles produced out of {total_tiles} candidates")


def main() -> None:
    args = parse_args()

    records = load_bounds(args.source_name)
    print(f"Loaded metadata for {len(records)} GeoTIFF files")

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

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tiles = generate_aggregated_tiles(
        records=records,
        min_zoom=args.min_zoom,
        max_zoom=max_zoom,
        bbox_wgs84=bbox,
        progress_interval=args.progress_interval,
    )

    create_pmtiles(tiles, output_path)


if __name__ == "__main__":
    main()
