#!/usr/bin/env python3
"""tmp_usage_benchmark.py

Create concurrent temporary files and measure peak usage of the target tmpdir.

Usage examples:
  python scripts/tmp_usage_benchmark.py --tmpdir /tmp --files 100 --size-kb 1024 --concurrency 4

The script writes N files of given size (KB) using a ThreadPoolExecutor and polls
the target directory to compute the peak used bytes during the run. The results
are printed as JSON and saved to `benchmark-<timestamp>.json` in the target dir.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from random import randbytes


def dir_size_bytes(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                fp = os.path.join(root, f)
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def write_file(path: Path, size_kb: int) -> Path:
    buf = randbytes(max(1, size_kb * 1024))
    with open(path, "wb") as fh:
        fh.write(buf)
    return path


def run_benchmark(tmpdir: str, files: int, size_kb: int, concurrency: int, poll_interval: float, cleanup: bool):
    tmp = Path(tmpdir)
    tmp.mkdir(parents=True, exist_ok=True)

    created = []
    peak = 0
    start = time.time()

    stop_monitor = threading.Event()

    def monitor():
        nonlocal peak
        while not stop_monitor.is_set():
            s = dir_size_bytes(tmp)
            if s > peak:
                peak = s
            time.sleep(poll_interval)

    mon = threading.Thread(target=monitor, daemon=True)
    mon.start()

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = []
        for i in range(files):
            fn = tmp / f"bench-{int(time.time()*1000)}-{i}.tmp"
            futures.append(ex.submit(write_file, fn, size_kb))

        for fut in as_completed(futures):
            try:
                p = fut.result()
                created.append(str(p))
            except Exception as e:
                created.append(f"ERROR: {e}")

    # Final poll
    time.sleep(poll_interval)
    final = dir_size_bytes(tmp)
    if final > peak:
        peak = final

    stop_monitor.set()
    mon.join(timeout=1.0)

    elapsed = time.time() - start

    out = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "tmpdir": str(tmp),
        "files_requested": files,
        "file_size_kb": size_kb,
        "concurrency": concurrency,
        "elapsed_sec": elapsed,
        "total_written_bytes": sum(os.path.getsize(p) for p in created if os.path.exists(p)) if created else 0,
        "peak_tmp_bytes": peak,
        "final_tmp_bytes": final,
        "created_files": len([p for p in created if os.path.exists(p)]),
    }

    out_path = tmp / f"benchmark-{int(time.time())}.json"
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)

    if cleanup:
        for p in created:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    return out, str(out_path)


def main():
    p = argparse.ArgumentParser(description="Temporary-dir usage benchmark")
    p.add_argument("--tmpdir", default=os.environ.get("TMPDIR", "/tmp"))
    p.add_argument("--files", type=int, default=50)
    p.add_argument("--size-kb", type=int, default=1024)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--poll-interval", type=float, default=0.05)
    p.add_argument("--no-cleanup", dest="cleanup", action="store_false")
    args = p.parse_args()

    out, out_path = run_benchmark(args.tmpdir, args.files, args.size_kb, args.concurrency, args.poll_interval, args.cleanup)
    print(json.dumps(out, indent=2))
    print(f"Saved summary to: {out_path}")


if __name__ == "__main__":
    main()
