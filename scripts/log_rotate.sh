#!/usr/bin/env bash
# Simple log rotation script for fusi output directory
# Rotates matching files, compresses older entries, and deletes very old archives.
#
# Usage:
#   ./scripts/log_rotate.sh --dir /path/to/output --keep 7 --compress-day 1 --max-age 30
#
set -euo pipefail

OUT_DIR="output"
KEEP=7            # keep this many recent archives (per pattern)
COMPRESS_AFTER=1  # days after which to compress files
MAX_AGE=30        # days after which to delete compressed archives
PATTERNS=("aggregate_run_*.log" "remote_mem_*.csv" "*.log")

usage(){
  cat <<USAGE
Usage: $0 [--dir DIR] [--keep N] [--compress-day N] [--max-age N]

Defaults: dir=output keep=7 compress-day=1 max-age=30
This script compresses files older than compress-day days, and removes compressed
archives older than max-age days. It keeps the most recent 'keep' archives per pattern.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) OUT_DIR="$2"; shift 2;;
    --keep) KEEP="$2"; shift 2;;
    --compress-day) COMPRESS_AFTER="$2"; shift 2;;
    --max-age) MAX_AGE="$2"; shift 2;;
    --help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

if [ ! -d "$OUT_DIR" ]; then
  echo "Output dir '$OUT_DIR' does not exist. Nothing to rotate." >&2
  exit 0
fi

cd "$OUT_DIR"

echo "Rotating logs in: $(pwd)"

# Compress older files matching patterns
for pat in "${PATTERNS[@]}"; do
  # find files older than COMPRESS_AFTER days that are not already gzipped
  find . -maxdepth 1 -type f -name "$pat" -mtime +$COMPRESS_AFTER ! -name "*.gz" -print0 |
    while IFS= read -r -d '' f; do
      echo "Compressing $f"
      gzip -9 -- "$f" || echo "gzip failed for $f"
    done
done

# Remove archives older than MAX_AGE days
find . -maxdepth 1 -type f -name "*.gz" -mtime +$MAX_AGE -print0 | while IFS= read -r -d '' old; do
  echo "Removing old archive: $old"
  rm -f -- "$old" || true
done

# Optionally keep only the most recent $KEEP archives per pattern
for pat in "${PATTERNS[@]}"; do
  # list gz files matching pattern.gz
  files=( $(ls -1t ${pat}.gz 2>/dev/null || true) )
  if [ ${#files[@]} -le $KEEP ]; then
    continue
  fi
  # remove files beyond KEEP
  idx=0
  for f in "${files[@]}"; do
    idx=$((idx+1))
    if [ $idx -le $KEEP ]; then
      continue
    fi
    echo "Pruning archived file: $f"
    rm -f -- "$f" || true
  done
done

echo "Rotation complete."
