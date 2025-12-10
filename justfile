# Justfile for fusi - Japanese elevation data to Terrarium tiles
# Following mapterhorn methodology with Terrarium encoding
#
# Current pipeline:
#   1. `just bounds <source>` to record GeoTIFF metadata
#   2. `just aggregate <source>` to build Terrarium MBTiles (defaults to output/fusi.mbtiles)

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

# 5. Aggregate: Merge one or more sources into one MBTiles, then PMTiles
#    (defaults: PMTiles=output/fusi.pmtiles, MBTiles=output/fusi.mbtiles)
# Usage:
#   just aggregate dem1a
#   just aggregate dem1a dem10b
#   just aggregate -o output/dem1a+dem10b.pmtiles dem1a dem10b
aggregate *args:
    #!/usr/bin/env bash
    set -euo pipefail

    # Populate shell positional params from just's arguments
    set -- {{args}}

    if [ "$#" -lt 1 ]; then
        echo "Usage: just aggregate <source...> [--options...]"
        echo "  e.g. just aggregate dem1a"
        echo "       just aggregate dem1a dem10b"
        echo "       just aggregate -o output/dem1a+dem10b.pmtiles dem1a dem10b"
        exit 1
    fi

    # Default output directory used for TMPDIR when not overridden by -o/--output
    mkdir -p "{{output_dir}}"
    export TMPDIR="$(cd "{{output_dir}}" && pwd)"
    # Keep GDAL cache modest unless overridden by user
    export GDAL_CACHEMAX="${GDAL_CACHEMAX:-512}"

    # Pass everything through to the Python CLI。
    # Python側で:
    #   -o/--output で「最終的な PMTiles パス」を決める（デフォルト: output/fusi.pmtiles）
    #   内部では同名で拡張子を .mbtiles にしたファイルに MBTiles を書く
    #   位置引数 sources... で dem1a dem10b ... を受け取る

    # PMTiles/MBTiles パスを決定（-o/--output があれば尊重）
    pmtiles_path="{{output_dir}}/fusi.pmtiles"
    i=1
    while [ $i -le "$#" ]; do
        arg="${!i}"
        if [ "$arg" = "-o" ] || [ "$arg" = "--output" ]; then
            j=$((i + 1))
            if [ $j -le "$#" ]; then
                pmtiles_path="${!j}"
            fi
            break
        fi
        i=$((i + 1))
    done

    mbtiles_path="${pmtiles_path%.pmtiles}.mbtiles"

    pipenv run python -u -m pipelines.aggregate_pmtiles \
        --verbose \
        --emit-lineage \
        "$@"

    # MBTiles → PMTiles 変換
    if command -v pmtiles >/dev/null 2>&1; then
        echo "Converting MBTiles to PMTiles: $mbtiles_path -> $pmtiles_path"
        pmtiles convert "$mbtiles_path" "$pmtiles_path"
    else
        echo "Warning: 'pmtiles' command not found; skipping PMTiles conversion."
        echo "         MBTiles is available at: $mbtiles_path"
    fi

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

# 10. Aggregate with zoom splitting (memory-optimized)
aggregate-split *args:
    #!/usr/bin/env bash
    set -euo pipefail
    # Populate positional params from just's arguments
    set -- {{args}}
    mkdir -p "{{output_dir}}"
    export TMPDIR="$(cd "{{output_dir}}" && pwd)"
    export GDAL_CACHEMAX="${GDAL_CACHEMAX:-512}"
    
    pipenv run python -u -m pipelines.split_aggregate \
        --verbose \
        "$@"

# 11. Aggregate specific zoom range only
aggregate-zoom min_zoom max_zoom *args:
    #!/usr/bin/env bash
    set -euo pipefail
    # Populate positional params from just's arguments
    set -- {{args}}
    mkdir -p "{{output_dir}}"
    export TMPDIR="$(cd "{{output_dir}}" && pwd)"
    export GDAL_CACHEMAX="${GDAL_CACHEMAX:-512}"
    
    pipenv run python -u -m pipelines.aggregate_by_zoom \
        --min-zoom {{min_zoom}} \
        --max-zoom {{max_zoom}} \
        --verbose \
        "$@"

# 12. Merge multiple MBTiles files
merge-mbtiles output_path *input_paths:
    pipenv run python pipelines/merge_mbtiles.py \
        --output "{{output_path}}" \
        {{input_paths}}

# 13. Show zoom split patterns
show-split-patterns:
    @echo "Available split patterns:"
    @echo ""
    @pipenv run python pipelines/zoom_split_config.py --pattern balanced
    @echo ""
    @echo "Other patterns: safe, fast, incremental, single"
    @echo "Use: pipenv run python pipelines/zoom_split_config.py --pattern <name>"

# 14. Upload: Sync PMTiles to remote host
upload:
    #!/usr/bin/env bash
    set -euo pipefail
    src="{{output_dir}}/fusi.pmtiles"
    if [ ! -f "$src" ]; then
        echo "Error: $src not found. Run just aggregate first."
        exit 1
    fi
    rsync -av --progress "$src" "pod@pod.local:/home/pod/x-24b/data/"
