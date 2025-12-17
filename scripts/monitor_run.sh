#!/usr/bin/env bash
# Simple monitor helper for running aggregate jobs
# Usage: ./scripts/monitor_run.sh <PID> [outdir]
# Collects: ps sampling (RSS/%mem), iostat, and (on macOS) fs_usage for the PID

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <PID> [outdir]"
  exit 2
fi

PID="$1"
OUTDIR="${2:-output/monitor_logs}"
mkdir -p "$OUTDIR"

SAMPLE_INTERVAL=${SAMPLE_INTERVAL:-5}

TS=$(date -u +%FT%TZ)
echo "monitor_start=${TS}" > "$OUTDIR/monitor_${PID}.meta"
echo "pid=${PID}" >> "$OUTDIR/monitor_${PID}.meta"
echo "interval_seconds=${SAMPLE_INTERVAL}" >> "$OUTDIR/monitor_${PID}.meta"

echo "Starting monitor for PID=$PID -> logs in: $OUTDIR"

# ps sampling (background)
PS_LOG="$OUTDIR/process_${PID}.log"
(
  echo "# timestamp pid %cpu %mem rss_kB cmd" >> "$PS_LOG"
  while kill -0 "$PID" 2>/dev/null; do
    date -u +%FT%TZ >> "$PS_LOG"
    # ps output; on macOS rss is in bytes, convert to kB for readability
    ps -p "$PID" -o pid=,%cpu=,%mem=,rss=,comm= | awk '{printf "%s %s\n", $0, ""}' >> "$PS_LOG"
    sleep "$SAMPLE_INTERVAL"
  done
  echo "# process $PID has exited" >> "$PS_LOG"
) &
PS_PID=$!

# iostat logging (if available)
IO_LOG="$OUTDIR/iostat.log"
if command -v iostat >/dev/null 2>&1; then
  echo "# iostat log started at $(date -u +%FT%TZ)" >> "$IO_LOG"
  ( iostat -d "$SAMPLE_INTERVAL" >> "$IO_LOG" ) &
  IOSTAT_PID=$!
else
  echo "# iostat not found; skipping" >> "$IO_LOG"
  IOSTAT_PID=""
fi

# macOS: fs_usage capture (requires sudo). On Linux this will be skipped.
FS_LOG="$OUTDIR/fs_usage_${PID}.log"
if [[ "$(uname -s)" == "Darwin" ]] && command -v fs_usage >/dev/null 2>&1; then
  echo "# fs_usage capturing to $FS_LOG (requires sudo)" >> "$FS_LOG"
  echo "If prompted for password, please enter it. To stop fs_usage press Ctrl-C or kill the monitor script." 
  ( sudo fs_usage -w -f filesys -p "$PID" > "$FS_LOG" ) &
  FS_PID=$!
else
  echo "# fs_usage not available or not macOS; skipping" >> "$FS_LOG"
  FS_PID=""
fi

# Save pids of background monitors so user can stop them later
echo "$PS_PID" > "$OUTDIR/monitor_${PID}.pids"
echo "$IOSTAT_PID" >> "$OUTDIR/monitor_${PID}.pids"
echo "$FS_PID" >> "$OUTDIR/monitor_${PID}.pids"

echo "MONITOR_PIDS: ps=$PS_PID iostat=$IOSTAT_PID fs_usage=$FS_PID"
echo "To stop monitors:"
echo "  kill $PS_PID ${IOSTAT_PID:-} ${FS_PID:-} || true"
echo "  rm -f $OUTDIR/monitor_${PID}.pids"

exit 0
