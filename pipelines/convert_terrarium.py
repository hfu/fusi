#!/usr/bin/env python3
"""
Convert GeoTIFF elevation data to PMTiles with Terrarium encoding.
Following mapterhorn methodology for terrain RGB encoding.

Usage:
    python pipelines/convert_terrarium.py <input_tif> <output_pmtiles> [--min-zoom MIN] [--max-zoom MAX]

Example:
    python pipelines/convert_terrarium.py input/sample.tif output/sample.pmtiles --min-zoom 0 --max-zoom 15
"""

import sys
import argparse
import math
import tempfile
import shutil
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, calculate_default_transform, Resampling
from rasterio.io import MemoryFile
import mercantile
import imagecodecs
from pmtiles.tile import zxy_to_tileid, TileType, Compression
from pmtiles.writer import Writer


def get_vertical_resolution(z):
    """
    Get vertical resolution for a given zoom level following mapterhorn methodology.
    
    Terrarium has maximal resolution of 1/256 m (~3.9 mm) at zoom 19.
    At lower zoom levels, vertical data is rounded to powers of 2.
    
    Returns factor to use for rounding elevation data.
    """
    full_resolution_zoom = 19
    factor = 2 ** (full_resolution_zoom - z) / 256
    return factor


def encode_terrarium(data, z):
    """
    Encode elevation data as Terrarium RGB.
    
    Terrarium encoding formula:
    - elevation in meters is encoded into RGB channels
    - Offset by +32768 to handle negative elevations
    - R = (elevation + 32768) // 256
    - G = (elevation + 32768) % 256
    - B = fractional part * 256
    
    Args:
        data: numpy array of elevation values in meters
        z: zoom level (for vertical resolution rounding)
    
    Returns:
        RGB numpy array of shape (512, 512, 3) with uint8 dtype
    """
    # Apply zoom-level specific vertical resolution rounding
    factor = get_vertical_resolution(z)
    data = np.round(data / factor) * factor
    
    # Offset for terrarium encoding
    data_offset = data + 32768
    
    # Encode to RGB
    rgb = np.zeros((512, 512, 3), dtype=np.uint8)
    rgb[..., 0] = np.clip(data_offset // 256, 0, 255).astype(np.uint8)
    rgb[..., 1] = np.clip(data_offset % 256, 0, 255).astype(np.uint8)
    rgb[..., 2] = np.clip((data_offset - np.floor(data_offset)) * 256, 0, 255).astype(np.uint8)
    
    return rgb


def reproject_to_webmercator(src_path, target_crs='EPSG:3857'):
    """
    Reproject GeoTIFF to Web Mercator (EPSG:3857).
    
    Args:
        src_path: Path to source GeoTIFF
        target_crs: Target CRS (default: EPSG:3857)
    
    Returns:
        MemoryFile with reprojected data
    """
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds
        )
        
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': target_crs,
            'transform': transform,
            'width': width,
            'height': height
        })
        
        memfile = MemoryFile()
        with memfile.open(**kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=Resampling.bilinear
                )
    
    return memfile


def generate_tiles(src_path, min_zoom, max_zoom):
    """
    Generate terrain tiles from GeoTIFF with Terrarium encoding.
    
    Args:
        src_path: Path to source GeoTIFF (should be in EPSG:3857)
        min_zoom: Minimum zoom level
        max_zoom: Maximum zoom level
    
    Yields:
        Tuple of (z, x, y, webp_data)
    """
    with rasterio.open(src_path) as src:
        # Get bounds in lat/lon for mercantile
        bounds = src.bounds
        west, south = rasterio.warp.transform('EPSG:3857', 'EPSG:4326', [bounds.left], [bounds.bottom])
        east, north = rasterio.warp.transform('EPSG:3857', 'EPSG:4326', [bounds.right], [bounds.top])
        
        west, south, east, north = west[0], south[0], east[0], north[0]
        
        for z in range(min_zoom, max_zoom + 1):
            # Get tiles that intersect the bounds
            tiles = list(mercantile.tiles(west, south, east, north, z))
            
            print(f'Zoom {z}: generating {len(tiles)} tiles')
            
            for tile in tiles:
                try:
                    # Get tile bounds in EPSG:3857
                    tile_bounds = mercantile.xy_bounds(tile)
                    
                    # Create window for this tile
                    window = rasterio.windows.from_bounds(
                        tile_bounds.left, tile_bounds.bottom,
                        tile_bounds.right, tile_bounds.top,
                        src.transform
                    )
                    
                    # Read and resample to 512x512
                    data = src.read(
                        1,
                        window=window,
                        out_shape=(512, 512),
                        resampling=Resampling.bilinear
                    )
                    
                    # Skip tiles with all nodata
                    if src.nodata is not None:
                        if np.all(data == src.nodata) or np.all(np.isnan(data)):
                            continue
                    
                    # Replace nodata with 0 (sea level)
                    if src.nodata is not None:
                        data = np.where(data == src.nodata, 0, data)
                    data = np.nan_to_num(data, nan=0.0)
                    
                    # Encode as Terrarium
                    rgb = encode_terrarium(data, z)
                    
                    # Encode as lossless WebP
                    webp_data = imagecodecs.webp_encode(rgb, lossless=True)
                    
                    yield (z, tile.x, tile.y, webp_data)
                
                except Exception as e:
                    print(f'Warning: Failed to generate tile {z}/{tile.x}/{tile.y}: {e}')
                    continue


def create_pmtiles(tiles_generator, output_path):
    """
    Create PMTiles archive from generated tiles.
    
    Args:
        tiles_generator: Generator yielding (z, x, y, webp_data) tuples
        output_path: Path to output PMTiles file
    """
    with open(output_path, 'wb') as f:
        writer = Writer(f)
        
        min_z = math.inf
        max_z = 0
        min_lon = math.inf
        min_lat = math.inf
        max_lon = -math.inf
        max_lat = -math.inf
        
        tile_count = 0
        
        # Stream tiles to a temporary file to avoid loading all into memory
        import pickle
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            tmpfile_path = tmpfile.name
            for z, x, y, webp_data in tiles_generator:
                tile_id = zxy_to_tileid(z=z, x=x, y=y)
                # Write a tuple (tile_id, webp_data) to the temp file
                pickle.dump((tile_id, webp_data), tmpfile)

                # Update bounds
                max_z = max(max_z, z)
                min_z = min(min_z, z)
                bounds = mercantile.bounds(x, y, z)
                min_lon = min(min_lon, bounds.west)
                min_lat = min(min_lat, bounds.south)
                max_lon = max(max_lon, bounds.east)
                max_lat = max(max_lat, bounds.north)

                tile_count += 1

        print(f'Writing {tile_count} tiles to PMTiles...')

        # Read tiles from temp file, sort by tile_id, and write to PMTiles
        tiles_iter = []
        with open(tmpfile_path, 'rb') as tmpfile:
            try:
                while True:
                    tile_id, webp_data = pickle.load(tmpfile)
                    tiles_iter.append((tile_id, webp_data))
            except EOFError:
                pass
        # Remove the temp file
        import os
        os.remove(tmpfile_path)
        # Sort by tile_id for efficient PMTiles structure
        tiles_iter.sort(key=lambda x: x[0])
        # Write tiles
        for tile_id, webp_data in tiles_iter:
            writer.write_tile(tile_id, webp_data)
        # Finalize with metadata
        min_lon_e7 = int(min_lon * 1e7)
        min_lat_e7 = int(min_lat * 1e7)
        max_lon_e7 = int(max_lon * 1e7)
        max_lat_e7 = int(max_lat * 1e7)
        
        writer.finalize(
            {
                'tile_type': TileType.WEBP,
                'tile_compression': Compression.NONE,
                'min_zoom': min_z,
                'max_zoom': max_z,
                'min_lon_e7': min_lon_e7,
                'min_lat_e7': min_lat_e7,
                'max_lon_e7': max_lon_e7,
                'max_lat_e7': max_lat_e7,
                'center_zoom': int(0.5 * (min_z + max_z)),
                'center_lon_e7': int(0.5 * (min_lon_e7 + max_lon_e7)),
                'center_lat_e7': int(0.5 * (min_lat_e7 + max_lat_e7)),
            },
            {
                'attribution': '国土地理院 (GSI Japan)',
                'encoding': 'terrarium',
                'vertical_resolution': 'zoom-dependent (mapterhorn compatible)',
            },
        )
        
        print(f'Successfully created {output_path}')


def main():
    parser = argparse.ArgumentParser(
        description='Convert GeoTIFF elevation data to PMTiles with Terrarium encoding'
    )
    parser.add_argument('input', help='Input GeoTIFF file')
    parser.add_argument('output', help='Output PMTiles file')
    parser.add_argument('--min-zoom', type=int, default=0, help='Minimum zoom level (default: 0)')
    parser.add_argument('--max-zoom', type=int, default=15, help='Maximum zoom level (default: 15)')
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f'Error: Input file {input_path} does not exist')
        sys.exit(1)
    
    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f'Converting {input_path} to {output_path}')
    print(f'Zoom levels: {args.min_zoom} to {args.max_zoom}')
    print(f'Encoding: Terrarium (mapterhorn compatible)')
    
    # Step 1: Reproject to Web Mercator if needed
    print('Step 1: Checking projection...')
    with rasterio.open(input_path) as src:
        if src.crs != 'EPSG:3857':
            print(f'  Reprojecting from {src.crs} to EPSG:3857...')
            with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as tmp:
                tmp_path = tmp.name
            
            memfile = reproject_to_webmercator(input_path)
            with memfile.open() as mem_src:
                with rasterio.open(tmp_path, 'w', **mem_src.meta) as dst:
                    dst.write(mem_src.read())
            
            processing_path = tmp_path
            try:
                # Step 2: Generate tiles
                print('Step 2: Generating tiles with Terrarium encoding...')
                tiles_gen = generate_tiles(processing_path, args.min_zoom, args.max_zoom)
                
                # Step 3: Create PMTiles
                print('Step 3: Creating PMTiles archive...')
                create_pmtiles(tiles_gen, output_path)
            finally:
                # Cleanup temporary file
                Path(processing_path).unlink()
        else:
            print('  Already in EPSG:3857')
            processing_path = str(input_path)
            # Step 2: Generate tiles
            print('Step 2: Generating tiles with Terrarium encoding...')
            tiles_gen = generate_tiles(processing_path, args.min_zoom, args.max_zoom)
            
            # Step 3: Create PMTiles
            print('Step 3: Creating PMTiles archive...')
            create_pmtiles(tiles_gen, output_path)
    
    print('Conversion complete!')


if __name__ == '__main__':
    main()
