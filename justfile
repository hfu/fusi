# Justfile for fusi - Japanese elevation data to PMTiles converter
# Following mapterhorn methodology with Terrarium encoding
#
# Pipeline: GeoTIFF → bounds.csv → Terrarium-encoded WebP tiles → PMTiles
# Two-stage approach:
#   1. Generate bounds.csv metadata for all GeoTIFFs
#   2. Convert to Terrarium-encoded PMTiles with zoom-dependent vertical resolution

source_dir := "source-store"
output_dir := "output"

default:
    @just --list

# 1. Setup: Install dependencies
install:
    pipenv install

setup: install
    @echo "Setup complete. Dependencies installed."

# 2. Bounds: Generate bounds.csv for a source
bounds source_name:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Generating bounds.csv for {{source_name}}..."
    mkdir -p "{{source_dir}}/{{source_name}}"
    pipenv run python pipelines/source_bounds.py "{{source_name}}"

# 3. Convert: Single file (GeoTIFF → Terrarium PMTiles)
convert input_file output_file min_zoom="0" max_zoom="15":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "$(dirname "{{output_file}}")"
    pipenv run python pipelines/convert_terrarium.py "{{input_file}}" "{{output_file}}" \
        --min-zoom {{min_zoom}} --max-zoom {{max_zoom}}

# 4. Test: Convert sample file from source-store
test-sample source_name:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p {{output_dir}}
    first_file=$(find -L "{{source_dir}}/{{source_name}}" -name "*.tif" | head -1)
    if [ -z "$first_file" ]; then
        echo "Error: No .tif files found in {{source_dir}}/{{source_name}}"
        exit 1
    fi
    just convert "$first_file" "{{output_dir}}/sample.pmtiles"

# 5. Batch: Convert all files from a source (parallel processing)
batch-convert source_name:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p {{output_dir}}
    if ! command -v parallel &> /dev/null; then
        echo "Error: GNU Parallel not installed. Install with: brew install parallel (macOS) or sudo apt install parallel (Ubuntu)"
        exit 1
    fi
    find -L "{{source_dir}}/{{source_name}}" -name "*.tif" | \
        parallel just convert {} {{output_dir}}/{/.}.pmtiles

# 6. Clean: Remove output directory
clean:
    rm -rf {{output_dir}}

# 7. Clean all: Remove output and generated bounds
clean-all:
    rm -rf {{output_dir}}
    find {{source_dir}} -name "bounds.csv" -delete

# 8. Check: Verify system dependencies
check:
    @echo "Checking dependencies..."
    @which python3 || echo "❌ Python 3 not found"
    @pipenv --version || echo "❌ pipenv not found"
    @which parallel || echo "⚠️  GNU Parallel not found (optional, for batch processing)"
    @echo "✓ Dependency check complete"

# 9. Config: Show current configuration
config:
    @echo "=== Fusi Configuration ==="
    @echo "Source directory: {{source_dir}}"
    @echo "Output directory: {{output_dir}}"
    @echo "Default zoom: 0-15"
    @echo "Encoding: Terrarium (mapterhorn compatible)"
    @echo "Tile format: Lossless WebP"
    @echo "Tile size: 512×512 pixels"

# 10. Inspect: Show PMTiles metadata
inspect pmtiles_file:
    pipenv run python pipelines/inspect_pmtiles.py "{{pmtiles_file}}"