#!/usr/bin/env bash
"""Simple macOS memory monitor for remote hosts (slate).

Writes CSV lines with timestamp, total_bytes, free_bytes, active_bytes, inactive_bytes,
wire_count, compressed, and a short list of top python processes (pid:rss_kb:cmd).

Usage: scripts/remote_memory_monitor.sh --output <path> --interval <seconds> --samples <n>
"""
set -euo pipefail

OUT="output/mem_monitor.csv"
INTERVAL=30
SAMPLES=10

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

echo "timestamp,total_bytes,free_bytes,active_bytes,inactive_bytes,wired_bytes,compressed_pages,swap_used_bytes,top_python" > "$OUT"

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

  free_bytes=$(( (free_pages==""?0:free_pages) * (page_size==""?4096:page_size) ))
  active_bytes=$(( (active_pages==""?0:active_pages) * (page_size==""?4096:page_size) ))
  inactive_bytes=$(( (inactive_pages==""?0:inactive_pages) * (page_size==""?4096:page_size) ))
  wired_bytes=$(( (wired_pages==""?0:wired_pages) * (page_size==""?4096:page_size) ))
  compressed_bytes=$(( (compressed_pages==""?0:compressed_pages) * (page_size==""?4096:page_size) ))

  # swap used: use vm_stat for 'Pages occupied by compressor' approx
  swap_used=0
  # Top python processes: pid:rss_kb:cmd (top 5)
  top_python=$(ps -axo pid,rss,comm | awk '/python/ {printf "%s:%s:%s;", $1, $2, $3}' | head -c 1000 | tr -d '\n')

  echo "${ts},${total_bytes},${free_bytes},${active_bytes},${inactive_bytes},${wired_bytes},${compressed_pages},${swap_used},\"${top_python}\"" >> "$OUT"

  sleep "$INTERVAL"
done
