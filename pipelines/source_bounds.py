#!/usr/bin/env python3
"""
Generate bounds.csv for GeoTIFF files in a source directory.
Following mapterhorn methodology - extracts bounding box in EPSG:3857 and raster dimensions.

Usage:
    python pipelines/source_bounds.py <source_name>

Example:
    python pipelines/source_bounds.py japan_dem

Output:
    source-store/<source_name>/bounds.csv
"""

import sys
import math
from pathlib import Path
from glob import glob

import rasterio
from rasterio.warp import transform_bounds


def main():
    if len(sys.argv) < 2:
        print('Usage: python pipelines/source_bounds.py <source_name>')
        print('Example: python pipelines/source_bounds.py japan_dem')
        sys.exit(1)
    
    source = sys.argv[1]
    print(f'Creating bounds for {source}...')
    
    source_dir = Path(f'source-store/{source}')
    if not source_dir.exists():
        print(f'Error: source-store/{source}/ does not exist')
        sys.exit(1)
    
    filepaths = sorted(glob(f'source-store/{source}/*.tif'))
    
    if not filepaths:
        print(f'Warning: No .tif files found in source-store/{source}/')
        sys.exit(1)
    
    print(f'Found {len(filepaths)} GeoTIFF files')
    
    bounds_file_lines = ['filename,left,bottom,right,top,width,height\n']
    
    for j, filepath in enumerate(filepaths):
        try:
            with rasterio.open(filepath) as src:
                if src.crs is None:
                    raise ValueError(f'CRS not defined on {filepath}')
                
                # Transform bounds to EPSG:3857 (Web Mercator)
                left, bottom, right, top = transform_bounds(
                    src.crs, 'EPSG:3857', *src.bounds
                )
                
                # Check for valid bounds
                for num in [left, bottom, right, top]:
                    if not math.isfinite(num):
                        raise ValueError(
                            f'Number in bounds is not finite. '
                            f'src.bounds={src.bounds} src.crs={src.crs} '
                            f'bounds={(left, bottom, right, top)}'
                        )
                
                filename = Path(filepath).name
                bounds_file_lines.append(
                    f'{filename},{left},{bottom},{right},{top},{src.width},{src.height}\n'
                )
                
                if (j + 1) % 100 == 0:
                    print(f'Processed {j + 1} / {len(filepaths)}')
        
        except Exception as e:
            print(f'Error processing {filepath}: {e}')
            continue
    
    bounds_file = source_dir / 'bounds.csv'
    with open(bounds_file, 'w') as f:
        f.writelines(bounds_file_lines)
    
    print(f'Successfully created {bounds_file}')
    print(f'Total files processed: {len(bounds_file_lines) - 1}')


if __name__ == '__main__':
    main()
