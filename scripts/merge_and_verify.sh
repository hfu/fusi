#!/usr/bin/env bash
set -euo pipefail
# Usage: ./scripts/merge_and_verify.sh output/merged.mbtiles input1.mbtiles input2.mbtiles ... [--tmpdir /path/to/tmp]

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 OUTPUT_MB input1.mbtiles [input2.mbtiles ...] [--tmpdir /path]"
  exit 2
fi

OUTPUT="$1"
shift

# parse optional --tmpdir at end
TMPDIR=""
ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --tmpdir)
      shift
      TMPDIR="$1"
      shift
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

# Merge MBTiles (use python CLI)
echo "Merging ${ARGS[*]} -> $OUTPUT"
pipenv run python pipelines/merge_mbtiles.py --output "$OUTPUT" ${ARGS[*]}

# Convert to PMTiles if pmtiles available
PM_OUT="${OUTPUT%.mbtiles}.pmtiles"
if command -v pmtiles >/dev/null 2>&1; then
  echo "Converting $OUTPUT -> $PM_OUT"
  if [ -n "$TMPDIR" ]; then
    mkdir -p "$TMPDIR"
    export TMPDIR="$TMPDIR"
    echo "Using TMPDIR=$TMPDIR"
    pmtiles convert --tmpdir "$TMPDIR" "$OUTPUT" "$PM_OUT"
  else
    pmtiles convert "$OUTPUT" "$PM_OUT"
  fi

  echo "Verifying PMTiles archive"
  pmtiles verify "$PM_OUT"
  pmtiles show "$PM_OUT" --metadata
  echo "Writing sha256 for $PM_OUT"
  shasum -a 256 "$PM_OUT" > "$PM_OUT.sha256"
else
  echo "pmtiles CLI not found; skipping PMTiles conversion. MBTiles located at: $OUTPUT"
fi

# Finalize: print sizes
echo "Result files sizes:"
ls -lh "$OUTPUT" || true
[ -f "$PM_OUT" ] && ls -lh "$PM_OUT" || true

echo "Done"
