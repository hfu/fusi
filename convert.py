#!/usr/bin/env python3
"""
GeoTIFF to PMTiles converter for Japanese elevation data.
Based on mapterhorn methodology for terrain tile generation.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
import rasterio
from rasterio.warp import calculate_default_transform, reproject
from rasterio.enums import Resampling
import tempfile
import sqlite3
import math


def reproject_to_web_mercator(input_tif, output_tif):
    """
    Reproject GeoTIFF to Web Mercator (EPSG:3857)
    """
    with rasterio.open(input_tif) as src:
        # Calculate transform and dimensions for Web Mercator
        transform, width, height = calculate_default_transform(
            src.crs, 'EPSG:3857', src.width, src.height, *src.bounds
        )
        
        # Update metadata
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': 'EPSG:3857',
            'transform': transform,
            'width': width,
            'height': height
        })
        
        # Reproject and write
        with rasterio.open(output_tif, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs='EPSG:3857',
                    resampling=Resampling.bilinear
                )


def convert_to_pmtiles(input_tif, output_pmtiles, tile_format='WEBP', maxzoom=None, approval=None, webp_quality=80, webp_lossless=True, addo_resampling='average'):
    """
    Convert GeoTIFF to PMTiles using pmtiles CLI
    """
    # First, ensure we have a Web Mercator projection
    with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as temp_tif:
        temp_path = temp_tif.name
    
    try:
        # Reproject to Web Mercator
        print(f"Reprojecting {input_tif} to Web Mercator...")
        reproject_to_web_mercator(input_tif, temp_path)
        
        # Convert to MBTiles using GDAL (gdal_translate + gdaladdo)
        mbtiles_path = output_pmtiles.replace('.pmtiles', '.mbtiles')

        print("Converting to MBTiles (gdal_translate)...")
        # Build creation options safely as pairs of ['-co','KEY=VALUE']
        co_options = [f'TILE_FORMAT={tile_format}', 'ZOOM_LEVEL_STRATEGY=AUTO']
        if tile_format.upper() == 'WEBP':
            if webp_lossless:
                # Try a few common lossless flags (GDAL builds differ). These will be passed as -co KEY=VALUE.
                co_options.extend(['WEBP_LOSSLESS=TRUE', 'LOSSLESS=YES'])
                # Set quality to 100 for safety if a numeric quality is present
                try:
                    q = int(webp_quality)
                    if q > 0:
                        co_options.append('WEBP_QUALITY=100')
                except Exception:
                    pass
            else:
                if webp_quality is not None:
                    co_options.append(f'WEBP_QUALITY={int(webp_quality)}')

        translate_cmd = ['gdal_translate', '-of', 'MBTILES', '-a_srs', 'EPSG:3857', '-ot', 'Byte', '-scale']
        # append -co pairs
        for co in co_options:
            translate_cmd.extend(['-co', co])
        translate_cmd.extend([temp_path, mbtiles_path])
        result = subprocess.run(translate_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"GDAL translate error: {result.stderr}\n{result.stdout}")
            return False

        print("Building overviews (gdaladdo)...")
        # Build a pyramid of overviews; pick reasonable factors (2,4,8,...)
        overviews = [str(2**i) for i in range(1, 10)]  # 2,4,8,...,512
        # Use user-specified resampling for overviews (average is a good default for DEM downsampling)
        addo_cmd = ['gdaladdo', '-r', addo_resampling, mbtiles_path] + overviews
        result = subprocess.run(addo_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"GDAL addo error: {result.stderr}\n{result.stdout}")
            return False

        # Inject useful metadata into MBTiles (description, maxzoom, approval)
        conn = None
        try:
            conn = sqlite3.connect(mbtiles_path)
            cur = conn.cursor()
            # Ensure metadata table exists (gdal should have created it)
            if maxzoom is None:
                # Default for 1m DEM data: z=17 is appropriate in WebMercator (roughly 1 m/px at Japan latitudes)
                maxzoom_val = 17
            else:
                maxzoom_val = int(maxzoom)

            # Compose description including approval note
            desc = f"Elevation tiles (generated)."
            if approval:
                desc = desc + f" {approval}"

            # Insert or replace metadata keys
            cur.execute("INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)", ('description', desc))
            cur.execute("INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)", ('maxzoom', str(maxzoom_val)))
            # Also record any encoding/quality hints
            if tile_format:
                cur.execute("INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)", ('format', tile_format.lower()))
            if tile_format and tile_format.upper() == 'WEBP' and webp_quality is not None:
                cur.execute("INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)", ('webp_quality', str(int(webp_quality))))

            conn.commit()
        except Exception as e:
            print(f"Warning: failed to write metadata into MBTiles: {e}")
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

        # Convert MBTiles to PMTiles (requires pmtiles CLI)
        print("Converting MBTiles to PMTiles (pmtiles convert)...")
        pmtiles_cmd = ['pmtiles', 'convert', mbtiles_path, output_pmtiles]
        result = subprocess.run(pmtiles_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"PMTiles conversion error: {result.stderr}\n{result.stdout}")
            return False
        
        # Clean up MBTiles file
        if os.path.exists(mbtiles_path):
            os.remove(mbtiles_path)
            
        return True
        
    finally:
        # Clean up temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)


def main():
    parser = argparse.ArgumentParser(description='Convert GeoTIFF to PMTiles for terrain tiles')
    parser.add_argument('input_tif', help='Input GeoTIFF file path')
    parser.add_argument('output_pmtiles', help='Output PMTiles file path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--tile-format', default='WEBP', choices=['PNG', 'WEBP', 'JPEG'], help='Tile image format to write into MBTiles (default: WEBP)')
    parser.add_argument('--max-zoom', type=int, help='Max zoom level to record in metadata (default: 17 for 1m data)')
    parser.add_argument('--approval', type=str, default='測量法に基づく国土地理院長承認（使用）R 6JHs 133', help='Approval string to include in metadata')
    parser.add_argument('--webp-quality', type=int, default=80, help='WEBP quality hint for GDAL (when tile-format=WEBP and not lossless)')
    parser.add_argument('--webp-lossless', action='store_true', default=True, help='When set, request lossless WEBP encoding (recommended for DEM)')
    parser.add_argument('--addo-resampling', type=str, default='average', choices=['nearest','average','gauss','cubic','bilinear'], help='Resampling method for gdaladdo overviews')

    args = parser.parse_args()
    
    # Validate input file
    if not os.path.exists(args.input_tif):
        print(f"Error: Input file {args.input_tif} not found")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(args.output_pmtiles)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Perform conversion
    print(f"Converting {args.input_tif} to {args.output_pmtiles}")
    
    success = convert_to_pmtiles(
        args.input_tif,
        args.output_pmtiles,
        tile_format=args.tile_format,
        maxzoom=args.max_zoom,
        approval=args.approval,
        webp_quality=args.webp_quality,
        webp_lossless=args.webp_lossless,
        addo_resampling=args.addo_resampling,
    )
    
    if success:
        print(f"✅ Conversion completed: {args.output_pmtiles}")
    else:
        print(f"❌ Conversion failed")
        sys.exit(1)


if __name__ == "__main__":
    main()