#!/usr/bin/env bash
# Collect runtime diagnostics useful for estimating progress on slate-like hosts.
# Usage:
#   ./scripts/collect_runtime_status.sh /path/to/output-dir
# If no output dir is given, uses current dir and writes `runtime-diagnostics-<ts>.txt`.

set -eu

OUTDIR=${1:-.}
mkdir -p "$OUTDIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUTFILE="$OUTDIR/runtime-diagnostics-${TS}.txt"

echo "collecting runtime diagnostics to: $OUTFILE"

{
  echo "===== TIMESTAMP: $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
  echo

  echo "===== uname -a ====="
  uname -a || true
  echo

  echo "===== uptime ====="
  uptime || true
  echo

  echo "===== df -h (root, TMPDIR if set) ====="
  df -h / 2>/dev/null || true
  if [ -n "${TMPDIR-}" ]; then
    echo "-- TMPDIR: $TMPDIR --"
    df -h "$TMPDIR" 2>/dev/null || true
  else
    df -h /tmp 2>/dev/null || true
  fi
  echo

  echo "===== ps top memory/cpu for fusi/python processes ====="
  # Portable ps selection: show pid, rss, %mem, %cpu, etime, cmd
  if ps -o pid,ppid,cmd >/dev/null 2>&1; then
    ps -eo pid,ppid,%mem,%cpu,rss,etime,cmd --sort=-rss | egrep 'python|aggregate|fusi|mbtiles' || true
  fi
  echo

  echo "===== top (brief snapshot) ====="
  if command -v top >/dev/null 2>&1; then
    # macOS: top -l 1 | head -n 60 ; Linux: top -b -n 1 | head -n 60
    if top -l 1 >/dev/null 2>&1; then
      top -l 1 | head -n 120 || true
    else
      top -b -n 1 | head -n 120 || true
    fi
  fi
  echo

  echo "===== vm_stat (macOS) / free -h (Linux) ====="
  if command -v vm_stat >/dev/null 2>&1; then
    vm_stat || true
  elif command -v free >/dev/null 2>&1; then
    free -h || true
  fi
  echo

  echo "===== iostat (if available) ====="
  if command -v iostat >/dev/null 2>&1; then
    iostat -x 1 3 || true
  fi
  echo

  echo "===== Recently modified MBTiles and .wal files (top 200) ====="
  # Search in current dir recursively for mbtiles and wal-like files
  find . -type f \( -iname '*.mbtiles' -o -iname '*.mbtiles-wal' -o -iname '*.wal' \) -printf '%T+ %p\n' 2>/dev/null | sort -r | head -n 200 || \
    (find . -type f \( -iname '*.mbtiles' -o -iname '*wal*' \) -print -exec ls -lh {} \; 2>/dev/null | head -n 200) || true
  echo

  echo "===== writer.log files (recent) ====="
  find . -type f -name '*.writer.log' -mtime -7 -print -exec echo '--- tail of' {} \; -exec tail -n 200 {} \; 2>/dev/null || true
  echo

  echo "===== USS / uss summary CSV files (recent) ====="
  find . -type f -iname '*uss*.csv' -mtime -7 -print -exec echo '--- tail of' {} \; -exec tail -n 200 {} \; 2>/dev/null || true
  echo

  echo "===== disk usage top directories (depth=2) ====="
  du -sh ./* 2>/dev/null | sort -hr | head -n 50 || true
  echo

  echo "===== open files for python processes (lsof) ====="
  if command -v lsof >/dev/null 2>&1; then
    lsof -c python | head -n 200 || true
  fi
  echo

  echo "===== end of diagnostics ====="

} > "$OUTFILE" 2>&1

echo "wrote: $OUTFILE"

echo "You can download it via scp:"
echo "  scp $OUTFILE your_local_host:/path/to/dest/"

exit 0
