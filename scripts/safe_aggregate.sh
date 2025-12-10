#!/usr/bin/env bash
# Safe aggregate runner: set conservative env and run aggregate-split
# Usage: ./scripts/safe_aggregate.sh dem1a dem5a dem10a dem10b
set -euo pipefail

WORKDIR=$(pwd)
CD=
TMPDIR_OVERRIDE=""
if [ -d "/Volumes/Migrate-2025-04/github/fusi" ]; then
  CD="/Volumes/Migrate-2025-04/github/fusi"
elif [ -d "$WORKDIR" ]; then
  CD="$WORKDIR"
fi
cd "$CD"

# Allow an optional --tmpdir /path override before other args.
if [ "$#" -ge 2 ] && [ "$1" = "--tmpdir" ]; then
  TMPDIR_OVERRIDE="$2"
  shift 2
fi

if [ -n "$TMPDIR_OVERRIDE" ]; then
  export TMPDIR="$TMPDIR_OVERRIDE"
  echo "Using TMPDIR override: $TMPDIR"
else
  export TMPDIR="$CD/output"
  echo "Using TMPDIR default: $TMPDIR"
fi
export GDAL_CACHEMAX=64
export OMP_NUM_THREADS=1
export GDAL_NUM_THREADS=1

# Default to safe split; spawn-per-group is default-enabled in code
# Use `python -m pipelines.split_aggregate` fallback if `just` is not setup
if command -v just >/dev/null 2>&1; then
  just aggregate-split "$@" \
    -o output/fusi.pmtiles \
    --split-pattern safe \
    --keep-intermediates \
    --io-sleep-ms 2 \
    --warp-threads 1 \
    --verbose
else
  python3 -m pipelines.split_aggregate "$@" \
    -o output/fusi.pmtiles \
    --split-pattern safe \
    --keep-intermediates \
    --io-sleep-ms 2 \
    --warp-threads 1 \
    --verbose
fi
