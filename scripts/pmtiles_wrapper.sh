#!/usr/bin/env bash
set -euo pipefail
# Wrapper to convert MBTiles -> PMTiles writing tmp file in the same parent directory
# Usage: ./scripts/pmtiles_wrapper.sh input.mbtiles /path/to/output.pmtiles [TMP_DIR]
# If TMP_DIR is provided it will be used; otherwise temporary file is created next to output.

MBTILES=${1:?Usage: pmtiles_wrapper.sh input.mbtiles output.pmtiles [TMP_DIR]}
OUT_PM=${2:?}
TMP_DIR=${3:-}

OUT_DIR=$(dirname "$OUT_PM")

if [ -z "$TMP_DIR" ]; then
    # Default: use the output directory for temporary files
    TMP_DIR="$OUT_DIR"
fi

mkdir -p "$TMP_DIR"
TMP_PATH="$TMP_DIR/$(basename "$OUT_PM").tmp"

# Export TMPDIR so go-pmtiles (and other libs using os.TempDir) use this directory for temp files
export TMPDIR="$TMP_DIR"
echo "[pmtiles_wrapper] using TMPDIR=$TMPDIR"

echo "[pmtiles_wrapper] input: $MBTILES"
echo "[pmtiles_wrapper] output tmp: $TMP_PATH"

# Prefer go-pmtiles CLI if available (faster, and better streaming)
if command -v pmtiles >/dev/null 2>&1; then
    echo "[pmtiles_wrapper] Using go-pmtiles 'pmtiles convert'"
    # Pass --tmpdir explicitly for go-pmtiles (defensive + portable)
    pmtiles convert --tmpdir "$TMP_DIR" "$MBTILES" "$TMP_PATH"
    rc=$?
else
    echo "[pmtiles_wrapper] go-pmtiles not found; falling back to Python writer"
    python3 pipelines/mbtiles_to_pmtiles.py "$MBTILES" "$TMP_PATH"
    rc=$?
fi

if [ $rc -ne 0 ]; then
    echo "[pmtiles_wrapper] conversion failed (rc=$rc) - leaving tmp: $TMP_PATH"
    exit $rc
fi

echo "[pmtiles_wrapper] moving tmp -> final: $OUT_PM"
mv -v "$TMP_PATH" "$OUT_PM"
echo "[pmtiles_wrapper] done"
