#!/usr/bin/env python3
"""Estimate ETA from writer.log JSONL files.

This script scans for `*.writer.log` JSONL files (or accepts paths) and
computes a simple rate (wal_bytes / elapsed) over the recent window, then
estimates remaining time given a user-supplied remaining-bytes estimate or
by summing current .mbtiles sizes (if --target-bytes provided).

Usage examples:
  python scripts/estimate_eta_from_writerlog.py /path/to/some.writer.log
  python scripts/estimate_eta_from_writerlog.py --scan . --target-bytes 10000000000

Output is printed as a small JSON summary.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


def parse_jsonl(path: Path) -> List[Dict[str, Any]]:
    events = []
    with path.open('r') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events


def recent_rate(events: List[Dict[str, Any]], key: str = 'wal_bytes', window: int = 300) -> Dict[str, Any]:
    # events expected to have 'ts' (ISO) and key
    if not events:
        return {'rate_bps': 0, 'samples': 0}

    # convert ts to datetime
    parsed = []
    for e in events:
        ts = e.get('ts') or e.get('timestamp') or e.get('time')
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except Exception:
            continue
        v = e.get(key)
        if v is None:
            continue
        parsed.append((t, float(v)))

    if len(parsed) < 2:
        return {'rate_bps': 0, 'samples': len(parsed)}

    parsed.sort()
    # filter to last `window` seconds
    now = parsed[-1][0]
    cutoff = now.timestamp() - window
    recent = [(t, v) for (t, v) in parsed if t.timestamp() >= cutoff]
    if len(recent) < 2:
        recent = parsed[-min(len(parsed), 10):]

    t0, v0 = recent[0]
    t1, v1 = recent[-1]
    dt = (t1 - t0).total_seconds()
    if dt <= 0:
        return {'rate_bps': 0, 'samples': len(recent)}

    rate = (v1 - v0) / dt
    return {'rate_bps': rate, 'samples': len(recent), 'start_ts': t0.isoformat(), 'end_ts': t1.isoformat(), 'delta_bytes': v1 - v0, 'delta_seconds': dt}


def estimate_eta(rate_bps: float, remaining_bytes: float) -> float:
    if rate_bps <= 0:
        return math.inf
    return remaining_bytes / rate_bps


def main():
    p = argparse.ArgumentParser()
    p.add_argument('paths', nargs='*', help='paths to writer.log JSONL files')
    p.add_argument('--scan', help='directory to scan for writer.log', default=None)
    p.add_argument('--target-bytes', type=float, help='remaining bytes to write (optional)')
    p.add_argument('--window', type=int, default=300, help='recent window in seconds to compute rate')
    args = p.parse_args()

    files: List[Path] = []
    for pth in args.paths:
        files.append(Path(pth))
    if args.scan:
        for p in Path(args.scan).rglob('*.writer.log'):
            files.append(p)

    if not files:
        print('no writer.log files found', file=sys.stderr)
        sys.exit(2)

    # for simplicity choose the most recently modified file
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    chosen = files[0]

    events = parse_jsonl(chosen)
    r = recent_rate(events, window=args.window)

    summary = {
        'writer_log': str(chosen),
        'samples': r.get('samples', 0),
        'rate_bps': r.get('rate_bps', 0),
        'details': r,
    }

    remaining = None
    if args.target_bytes is not None:
        remaining = args.target_bytes
    else:
        remaining = None

    if remaining is not None:
        eta = estimate_eta(r.get('rate_bps', 0), remaining)
        summary['remaining_bytes'] = remaining
        summary['eta_seconds'] = eta
    else:
        summary['eta_seconds'] = None

    print(json.dumps(summary, indent=2, default=str))


if __name__ == '__main__':
    main()
