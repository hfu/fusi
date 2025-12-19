#!/usr/bin/env bash
set -euo pipefail

# Hybrid wrapper: given source names, produce per-source MBTiles sequentially,
# then run pixel-wise PMTiles merge (priority by default) and optionally
# remove intermediate MBTiles.

usage() {
  cat <<'EOF'
Usage: pixelwise_hybrid.sh [options] <source1> <source2> ...

Options:
  -o, --output PATH        Output PMTiles path (default: output/fusi.pmtiles)
  --mode MODE              Merge mode: priority|max (default: priority)
  --keep-intermediates    Keep per-source MBTiles after merge
  --tmpdir PATH            TMPDIR to pass to workers
  --io-sleep-ms N         io-sleep-ms for aggregator (default: 50)
  --warp-threads N        warp threads for aggregator (default: 1)
  --watchdog-memory-mb N  watchdog memory for aggregator workers
  --help                  Show this help
EOF
}

# Defaults
OUTPUT="output/fusi.pmtiles"
MODE="priority"
KEEP=0
TMPDIR_ENV=""
IO_SLEEP_MS=50
WARP_THREADS=1
WATCHDOG_MB=""

POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output)
      OUTPUT="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --keep-intermediates)
      KEEP=1
      shift
      ;;
    --tmpdir)
      TMPDIR_ENV="$2"
      shift 2
      ;;
    --io-sleep-ms)
      IO_SLEEP_MS="$2"
      shift 2
      ;;
    --warp-threads)
      WARP_THREADS="$2"
      shift 2
      ;;
    --watchdog-memory-mb)
      WATCHDOG_MB="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*|--*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done

if [ ${#POSITIONAL[@]} -eq 0 ]; then
  echo "Error: at least one source name is required" >&2
  usage
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"
mkdir -p output

MBLIST=()

for src in "${POSITIONAL[@]}"; do
  mb="output/${src}.mbtiles"
  echo "Producing per-source MBTiles for: $src -> $mb"

  # Ensure TMPDIR per-source if requested
  if [ -n "$TMPDIR_ENV" ]; then
    export TMPDIR="$TMPDIR_ENV/$src"
    mkdir -p "$TMPDIR"
  fi

  cmd=(pipenv run python -u -m pipelines.aggregate_pmtiles -o "$mb" --min-zoom 0 --max-zoom 16 --io-sleep-ms "$IO_SLEEP_MS" --warp-threads "$WARP_THREADS" --verbose --overwrite "$src")
  if [ -n "$WATCHDOG_MB" ]; then
    cmd+=(--watchdog-memory-mb "$WATCHDOG_MB")
  fi

  echo "Running: ${cmd[*]}"
  # Run and fail fast on error
  eval "${cmd[*]}"

  MBLIST+=("$mb")
done

# Now run pixel-wise PMTiles merge using per-source MBTiles in given order
echo "Merging per-source MBTiles into PMTiles: $OUTPUT (mode=$MODE)"
pipenv run python -u -m pipelines.merge_pmtiles_pixelwise "${MBLIST[@]}" -o "$OUTPUT" --mode "$MODE" --verbose

if [ $KEEP -eq 0 ]; then
  echo "Removing intermediate MBTiles..."
  for m in "${MBLIST[@]}"; do
    rm -f "$m"
  done
fi

echo "Pixel-wise hybrid merge complete: $OUTPUT"
