# Justfile for fusi - Japanese elevation data to PMTiles converter
#
# Pipeline: GeoTIFF (elevation) → rio-rgbify (Terrain-RGB MBTiles) → pmtiles (PMTiles)
# rio-rgbify handles: reprojection to EPSG:3857, RGB encoding, and MBTiles generation
# pmtiles handles: MBTiles to PMTiles conversion only

input_dir := "input"
output_dir := "output"

default:
    @just --list

# 1. Setup: Install dependencies
install:
    pipenv install

setup: install
    @which pmtiles > /dev/null || echo "⚠️  Install pmtiles: https://github.com/protomaps/go-pmtiles"
    @which parallel > /dev/null || echo "⚠️  Install parallel for batch processing"

# 2. Convert: Single file (GeoTIFF → Terrain-RGB PMTiles)
convert input_file output_file:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "$(dirname "{{output_file}}")"
    output="{{output_file}}"
    mbtiles="${output%.pmtiles}.mbtiles"
    pipenv run rio rgbify "{{input_file}}" "$mbtiles" --min-z 0 --max-z 15 --format mbtiles
    pmtiles convert "$mbtiles" "{{output_file}}"
    rm -f "$mbtiles"

# 3. Test: Convert sample file
test-sample:
    mkdir -p {{output_dir}}
    just convert "{{input_dir}}/$(ls {{input_dir}} | head -1)" "{{output_dir}}/sample.pmtiles"

# 4. Batch: Convert all files (parallel processing)
batch-convert:
    mkdir -p {{output_dir}}
    find {{input_dir}} -name "*.tif" | parallel just convert {} {{output_dir}}/{/.}.pmtiles

# 5. Clean: Remove output directory
clean:
    rm -rf {{output_dir}}