#!/usr/bin/env python3
"""
Example: End-to-end pipeline usage demonstration

This script shows how to use the fusi pipeline to:
1. Generate bounds.csv for GeoTIFF files
2. Convert a single GeoTIFF to PMTiles
3. Verify the output

Usage:
    python pipelines/example.py
"""

import sys
from pathlib import Path

# Add pipelines to path
sys.path.insert(0, str(Path(__file__).parent))

import source_bounds
import convert_terrarium


def main():
    print("=" * 60)
    print("Fusi Pipeline Example")
    print("=" * 60)
    
    # Check if test data exists
    test_dir = Path("source-store/test")
    if not test_dir.exists() or not list(test_dir.glob("*.tif")):
        print("\nError: No test data found in source-store/test/")
        print("Please run the test data creation first.")
        print("\nYou can create test data with:")
        print("  mkdir -p source-store/test")
        print("  # Then copy a GeoTIFF to source-store/test/")
        return 1
    
    print("\n1. Generating bounds.csv...")
    print("-" * 60)
    sys.argv = ["source_bounds.py", "test"]
    try:
        source_bounds.main()
    except SystemExit as e:
        if e.code != 0:
            return e.code
    
    print("\n2. Converting GeoTIFF to PMTiles...")
    print("-" * 60)
    input_file = list(test_dir.glob("*.tif"))[0]
    output_file = Path("output/example.pmtiles")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    sys.argv = [
        "convert_terrarium.py",
        str(input_file),
        str(output_file),
        "--min-zoom", "8",
        "--max-zoom", "12"
    ]
    try:
        convert_terrarium.main()
    except SystemExit as e:
        if e.code != 0:
            return e.code
    
    print("\n3. Verifying output...")
    print("-" * 60)
    if output_file.exists():
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"✓ Output file created: {output_file}")
        print(f"✓ Size: {size_mb:.2f} MB")
        
        # Check bounds.csv
        bounds_file = test_dir / "bounds.csv"
        if bounds_file.exists():
            with open(bounds_file) as f:
                lines = f.readlines()
            print(f"✓ Bounds file created with {len(lines)-1} entries")
        
        print("\n" + "=" * 60)
        print("Pipeline completed successfully!")
        print("=" * 60)
        print("\nYou can now:")
        print("1. View the PMTiles in a map viewer")
        print("2. Run batch processing with: just batch-convert test")
        print("3. Check metadata with pmtiles CLI tools")
        return 0
    else:
        print("✗ Output file not created")
        return 1


if __name__ == "__main__":
    sys.exit(main())
