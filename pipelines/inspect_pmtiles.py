#!/usr/bin/env python3
"""
Inspect PMTiles file metadata and header information.

Usage:
    python pipelines/inspect_pmtiles.py <pmtiles_file>
"""

import sys
from pathlib import Path
from pmtiles.reader import Reader, MemorySource


def main():
    if len(sys.argv) < 2:
        print("Usage: python pipelines/inspect_pmtiles.py <pmtiles_file>")
        sys.exit(1)
    
    pmtiles_file = Path(sys.argv[1])
    
    if not pmtiles_file.exists():
        print(f"Error: File not found: {pmtiles_file}")
        sys.exit(1)
    
    with open(pmtiles_file, 'rb') as f:
        data = f.read()
    
    source = MemorySource(data)
    reader = Reader(source)
    header = reader.header()
    metadata = reader.metadata()
    
    print(f"PMTiles File: {pmtiles_file}")
    print(f"Size: {len(data) / (1024*1024):.2f} MB")
    print(f"\nHeader:")
    print(f"  Zoom: {header['min_zoom']} - {header['max_zoom']}")
    print(f"  Bounds: ({header['min_lon_e7']/1e7:.4f}, {header['min_lat_e7']/1e7:.4f}) to ({header['max_lon_e7']/1e7:.4f}, {header['max_lat_e7']/1e7:.4f})")
    print(f"  Center: ({header['center_lon_e7']/1e7:.4f}, {header['center_lat_e7']/1e7:.4f}) @ zoom {header['center_zoom']}")
    print(f"  Tile Type: {header['tile_type']}")
    print(f"  Tile Compression: {header['tile_compression']}")
    
    if metadata:
        print(f"\nMetadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")


if __name__ == '__main__':
    main()
