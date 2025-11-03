# Justfile for fusi - Japanese elevation data to PMTiles converter
# Install just: https://github.com/casey/just

# Variables
input_dir := "input"
output_dir := "docs"

# Default recipe
default:
    @just --list

# Install dependencies using pipenv
install:
    @echo "Installing dependencies with pipenv..."
    pipenv install
    @echo "✅ Dependencies installed"

# Install development dependencies
install-dev:
    pipenv install --dev

# Clean output directory
clean:
    @echo "Cleaning old output directory (remove 'output' if present) and ensure {{output_dir}} exists..."
    rm -rf output || true
    mkdir -p {{output_dir}}
    @echo "✅ Cleaned. Docs output directory ready: {{output_dir}}"

# Convert a single GeoTIFF file to PMTiles
convert input_file output_file:
    @echo "Converting {{input_file}} to {{output_file}}"
    pipenv run python convert.py "{{input_file}}" "{{output_file}}"

# Convert a sample file for testing
test-sample:
    @echo "Testing conversion with the largest GeoTIFF file in {{input_dir}} (Python runner)..."
    pipenv run python scripts/test_sample.py --input {{input_dir}} --output {{output_dir}}/sample.pmtiles

# Batch convert all files in input directory (parallel processing)
batch-convert:
    @echo "Starting batch conversion of all GeoTIFF files..."
    mkdir -p {{output_dir}}
    find {{input_dir}} -name "*.tif" | parallel pipenv run python convert.py {} {{output_dir}}/{/.}.pmtiles

# Count input files
count-files:
    @echo "Counting GeoTIFF files in input directory..."
    @find {{input_dir}} -name "*.tif" | wc -l

# Show file size statistics
stats:
    @echo "Input directory statistics:"
    @du -h {{input_dir}} | tail -1
    @echo "Number of .tif files:"
    @find {{input_dir}} -name "*.tif" | wc -l
    @if [ -d "{{output_dir}}" ]; then \
        echo "Output directory statistics:"; \
        du -h {{output_dir}} | tail -1; \
        echo "Number of .pmtiles files:"; \
        find {{output_dir}} -name "*.pmtiles" | wc -l; \
    fi

# Setup development environment
setup: install
    @echo "Setting up development environment..."
    @echo "Checking for required tools..."
    @which gdal2tiles.py > /dev/null || echo "⚠️  gdal2tiles.py not found - install GDAL tools"
    @which pmtiles > /dev/null || echo "⚠️  pmtiles CLI not found - install from https://github.com/protomaps/go-pmtiles"
    @echo "✅ Development environment ready"

# Check dependencies and tools
check:
    @echo "Checking system dependencies..."
    @which python3 > /dev/null && echo "✅ Python3 found" || echo "❌ Python3 not found"
    @which pipenv > /dev/null && echo "✅ Pipenv found" || echo "❌ Pipenv not found"  
    @which gdal2tiles.py > /dev/null && echo "✅ GDAL tools found" || echo "⚠️  GDAL tools not found"
    @which pmtiles > /dev/null && echo "✅ PMTiles CLI found" || echo "⚠️  PMTiles CLI not found"
    @which parallel > /dev/null && echo "✅ GNU Parallel found" || echo "⚠️  GNU Parallel not found (for batch processing)"

# Vite/docs recipes removed — the site is now a minimal static `docs/index.html` + `docs/index.js`.
# To preview locally, serve the `docs/` directory with a static server, e.g.:
#   python3 -m http.server --directory docs 5173
# or use the convenience recipe below.
serve-docs:
    @echo "Serving docs/ statically on http://localhost:5173"
    @python3 -m http.server --directory docs 5173