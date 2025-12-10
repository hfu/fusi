#!/usr/bin/env bash
# Wrapper to start an aggregate (or any long-running command) with recommended env vars
# for slate to avoid system tmp saturation and limit GDAL/OMP memory usage.
#
# Usage: ./scripts/start_aggregate_with_env.sh --workdir /absolute/path --cmd "just aggregate-split dem10a dem10b"

set -euo pipefail

WORKDIR="$(pwd)"
TMPDIR_OVERRIDE=""
CMD=""

usage(){
  cat <<USAGE
Usage: $0 --workdir /abs/path --cmd "<command to run>" [--tmpdir /abs/path]

This script sets:
  TMPDIR (defaults to WORKDIR/output if writable, otherwise /tmp)
  GDAL_CACHEMAX=64
  OMP_NUM_THREADS=1
  GDAL_NUM_THREADS=1

It runs the command with stdout/stderr redirected to WORKDIR/output/aggregate_run.log
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workdir) WORKDIR="$2"; shift 2;;
    --tmpdir) TMPDIR_OVERRIDE="$2"; shift 2;;
    --cmd) CMD="$2"; shift 2;;
    --help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

if [ -z "$CMD" ]; then
  echo "--cmd is required" >&2; usage; exit 2
fi

mkdir -p "$WORKDIR/output"

if [ -n "$TMPDIR_OVERRIDE" ]; then
  TMPDIR="$TMPDIR_OVERRIDE"
else
  if [ -w "$WORKDIR/output" ]; then
    TMPDIR="$WORKDIR/output"
  else
    TMPDIR="/tmp"
  fi
fi

export TMPDIR
export GDAL_CACHEMAX=64
export OMP_NUM_THREADS=1
export GDAL_NUM_THREADS=1

LOGFILE="$WORKDIR/output/aggregate_run_$(date +%s).log"

echo "Starting command with envs: TMPDIR=$TMPDIR GDAL_CACHEMAX=$GDAL_CACHEMAX OMP_NUM_THREADS=$OMP_NUM_THREADS GDAL_NUM_THREADS=$GDAL_NUM_THREADS" | tee "$LOGFILE"

# Run the command in a nohup backgrounded shell so it survives disconnects.
nohup bash -lc "cd '$WORKDIR' && $CMD" >> "$LOGFILE" 2>&1 &
echo "PID:$!" >> "$LOGFILE"
echo "Launched. Log: $LOGFILE"
