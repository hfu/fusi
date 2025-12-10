#!/usr/bin/env bash
# Simple macOS memory monitor for remote hosts (slate)
#
# Writes CSV lines with timestamp, total_bytes, free_bytes, active_bytes, inactive_bytes,
# wired_bytes, compressed_pages, and a short list of top python processes (pid:rss_kb:cmd).
#
# Usage: scripts/remote_memory_monitor_fixed.sh --output <path> --interval <seconds> --samples <n>
set -euo pipefail

OUT="output/mem_monitor.csv"
INTERVAL=30
SAMPLES=10
TMPDIR_PATH="${TMPDIR:-/tmp}"

usage(){
  cat <<USAGE
Usage: $0 --output /abs/path.csv [--interval 30] [--samples 20]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUT="$2"; shift 2;;
    --interval) INTERVAL="$2"; shift 2;;
    --samples) SAMPLES="$2"; shift 2;;
    --help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

mkdir -p "$(dirname "$OUT")"

echo "timestamp,total_bytes,free_bytes,active_bytes,inactive_bytes,wired_bytes,compressed_pages,swap_used_bytes,tmpdir_free_bytes,tmpdir_path,gdal_cachemax,omp_num_threads,gdal_num_threads,top_python" > "$OUT"

for i in $(seq 1 "$SAMPLES"); do
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  # total memory
  total_bytes=$(sysctl -n hw.memsize 2>/dev/null || echo 0)

  # vm_stat: parse pages
  vm=$(vm_stat)
  page_size=$(sysctl -n hw.pagesize 2>/dev/null || echo 4096)
  free_pages=$(echo "$vm" | awk '/Pages free/ {print $3}' | tr -d '.')
  active_pages=$(echo "$vm" | awk '/Pages active/ {print $3}' | tr -d '.')
  inactive_pages=$(echo "$vm" | awk '/Pages inactive/ {print $3}' | tr -d '.')
  wired_pages=$(echo "$vm" | awk '/Pages wired down/ {print $4}' | tr -d '.')
  compressed_pages=$(echo "$vm" | awk '/Pages compressed/ {print $3}' | tr -d '.')

  # normalize empty values and compute byte counts
  free_pages=${free_pages:-0}
  active_pages=${active_pages:-0}
  inactive_pages=${inactive_pages:-0}
  wired_pages=${wired_pages:-0}
  compressed_pages=${compressed_pages:-0}
  page_size=${page_size:-4096}

  free_bytes=$(( free_pages * page_size ))
  active_bytes=$(( active_pages * page_size ))
  inactive_bytes=$(( inactive_pages * page_size ))
  wired_bytes=$(( wired_pages * page_size ))
  compressed_bytes=$(( compressed_pages * page_size ))

  # swap used: placeholder
  swap_used=0
  # disk free for TMPDIR_PATH (bytes)
  if [ -n "$TMPDIR_PATH" ]; then
    # prefer df -k then convert to bytes
    df_out=$(df -k "$TMPDIR_PATH" 2>/dev/null | tail -n1 || true)
    if [ -n "$df_out" ]; then
      avail_kb=$(echo "$df_out" | awk '{print $(NF-2)}')
      tmpdir_free_bytes=$(( ${avail_kb:-0} * 1024 ))
    else
      tmpdir_free_bytes=0
    fi
  else
    tmpdir_free_bytes=0
  fi
  tmpdir_path="$TMPDIR_PATH"
  gdal_cachemax="${GDAL_CACHEMAX:-}"
  omp_num_threads="${OMP_NUM_THREADS:-}"
  gdal_num_threads="${GDAL_NUM_THREADS:-}"
  # Top python processes: pid:rss_kb:cmd (top 5)
  top_python=$(ps -axo pid,rss,comm | awk '/python/ {printf "%s:%s:%s;", $1, $2, $3}' | head -c 1000 | tr -d '\n')

  echo "${ts},${total_bytes},${free_bytes},${active_bytes},${inactive_bytes},${wired_bytes},${compressed_pages},${swap_used},${tmpdir_free_bytes},${tmpdir_path},${gdal_cachemax},${omp_num_threads},${gdal_num_threads},\"${top_python}\"" >> "$OUT"

  sleep "$INTERVAL"
done
