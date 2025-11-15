# Justfile for fusi - Japanese elevation data to PMTiles converter
# Following mapterhorn methodology with Terrarium encoding
#
# Current pipeline:
#   1. `just bounds <source>` to record GeoTIFF metadata
#   2. `just aggregate <source>` to build Terrarium PMTiles (defaults to output/fusi.pmtiles)

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
convert input_file output_file min_zoom="0" max_zoom="":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "$(dirname "{{output_file}}")"
    max_zoom_arg=""
    if [ -n "{{max_zoom}}" ]; then
        max_zoom_arg="--max-zoom {{max_zoom}}"
    fi
    pipenv run python pipelines/convert_terrarium.py "{{input_file}}" "{{output_file}}" \
        --min-zoom {{min_zoom}} ${max_zoom_arg}

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

# 5. Aggregate: Merge multiple GeoTIFFs into one PMTiles (defaults to output/fusi.pmtiles)
aggregate source_name output_file="output/fusi.pmtiles" *extra_args:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "$(dirname "{{output_file}}")"
    pipenv run python pipelines/aggregate_pmtiles.py "{{source_name}}" "{{output_file}}" {{extra_args}}

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
    @echo "✓ Dependency check complete"

# 9. Inspect: Show PMTiles metadata
inspect pmtiles_file:
    pipenv run python pipelines/inspect_pmtiles.py "{{pmtiles_file}}"

# 10. Upload: Sync PMTiles to remote host
upload:
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{output_dir}}/fusi.pmtiles"
    if [ ! -f "$src" ]; then
        echo "Error: $src not found. Run just aggregate first."
        exit 1
    fi
    rsync -av --progress "$src" "pod@pod.local:/home/pod/x-24b/data/"
