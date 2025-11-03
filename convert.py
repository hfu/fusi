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
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.enums import Resampling
import tempfile


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


def convert_to_pmtiles(input_tif, output_pmtiles):
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
        
        # Convert to PMTiles using GDAL's gdal2tiles.py equivalent approach
        # For now, we'll use a simple GDAL command to create MBTiles first
        mbtiles_path = output_pmtiles.replace('.pmtiles', '.mbtiles')
        
        print(f"Converting to MBTiles format...")
        gdal_cmd = [
            'gdal2tiles.py',
            '-z', '0-15',  # Zoom levels 0 to 15
            '--profile=raster',
            '--format=mbtiles',
            temp_path,
            mbtiles_path
        ]
        
        result = subprocess.run(gdal_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"GDAL error: {result.stderr}")
            return False
        
        # Convert MBTiles to PMTiles (requires pmtiles CLI)
        print(f"Converting MBTiles to PMTiles...")
        pmtiles_cmd = ['pmtiles', 'convert', mbtiles_path, output_pmtiles]
        
        result = subprocess.run(pmtiles_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"PMTiles conversion error: {result.stderr}")
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
    
    success = convert_to_pmtiles(args.input_tif, args.output_pmtiles)
    
    if success:
        print(f"✅ Conversion completed: {args.output_pmtiles}")
    else:
        print(f"❌ Conversion failed")
        sys.exit(1)


if __name__ == "__main__":
    main()