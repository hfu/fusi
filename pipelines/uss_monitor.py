"""Lightweight USS (Unique Set Size) sampler.

Provides a small background sampler that records the peak USS (or falls
back to RSS if USS is unavailable) for the current Python process and
its children. Uses `psutil` when available, otherwise falls back to
reading RSS via the existing `memory_monitor` fallback.

The sampler is intentionally small and dependency-light: when `psutil`
is not installed it still provides an RSS-based peak which is useful
for coarse-grained measurements on CI or developer machines.
"""
from __future__ import annotations

import threading
import time
from typing import Optional
import csv
import os
from datetime import datetime

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional
    psutil = None

from .memory_monitor import get_rss_bytes


class USSMonitor:
    """Background sampler that records peak USS (or RSS fallback).

    Usage:
        monitor = USSMonitor(interval=0.5)
        monitor.start()
        do_work()
        monitor.stop()
        peak_bytes = monitor.peak_bytes
    """

    def __init__(
        self,
        interval: float = 0.5,
        output_csv: Optional[str] = None,
        track_children: bool = True,
        include_cpu: bool = True,
    ) -> None:
        self.interval = float(interval)
        self._peak: int = 0
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # CSV output (optional). If provided, sampler will append periodic
        # rows with timestamp,pid,cmd,uss,rss,vss,cpu_percent.
        self.output_csv = str(output_csv) if output_csv is not None else None
        self.track_children = bool(track_children)
        self.include_cpu = bool(include_cpu)
        self._csv_lock = threading.Lock()
        # If CSV path provided, ensure directory exists and write header when starting
        if self.output_csv:
            try:
                os.makedirs(os.path.dirname(self.output_csv) or ".", exist_ok=True)
            except Exception:
                pass

    @property
    def peak_bytes(self) -> int:
        return int(self._peak)

    def _sample_once(self) -> int:
        """Return the best-effort USS in bytes for this process tree.

        When psutil is available, try `memory_full_info().uss` where
        supported. Otherwise fall back to rss-summing of the process
        and its children, or finally to the fallback `get_rss_bytes()`.
        """
        if psutil is not None:
            try:
                proc = psutil.Process()
                # Try memory_full_info -> has `uss` on some platforms
                try:
                    mfi = proc.memory_full_info()
                    uss = getattr(mfi, "uss", None)
                    if uss:
                        return int(uss)
                except Exception:
                    pass

                # Sum resident set of process + children as a best-effort proxy
                total = proc.memory_info().rss
                try:
                    for child in proc.children(recursive=True):
                        try:
                            total += child.memory_info().rss
                        except Exception:
                            continue
                except Exception:
                    # children may fail on some platforms
                    pass
                return int(total)
            except Exception:
                # fall through
                pass

        # Fallback: use the existing RSS helper
        return int(get_rss_bytes())

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                v = self._sample_once()
                if v > self._peak:
                    self._peak = v
                # Optionally write a CSV row for visibility
                if self.output_csv:
                    try:
                        ts = datetime.utcnow().isoformat() + "Z"
                        pid = os.getpid()
                        cmd = ""
                        cpu = ""
                        rss = ""
                        vss = ""
                        uss = v
                        if psutil is not None:
                            try:
                                proc = psutil.Process()
                                cmd = " ".join(proc.cmdline() or [])
                                if self.include_cpu:
                                    try:
                                        cpu = f"{proc.cpu_percent(interval=None):.1f}"
                                    except Exception:
                                        cpu = ""
                                try:
                                    mi = proc.memory_info()
                                    rss = str(getattr(mi, "rss", ""))
                                    vss = str(getattr(mi, "vms", ""))
                                except Exception:
                                    pass
                            except Exception:
                                pass

                        row = [ts, pid, cmd, str(uss), rss, vss, cpu]
                        # write safely
                        with self._csv_lock:
                            write_header = not os.path.exists(self.output_csv)
                            with open(self.output_csv, "a", newline="", encoding="utf-8") as fh:
                                writer = csv.writer(fh)
                                if write_header:
                                    writer.writerow(["timestamp", "pid", "cmd", "uss_bytes", "rss_bytes", "vss_bytes", "cpu_percent"])
                                writer.writerow(row)
                    except Exception:
                        # CSV write must not crash sampler
                        pass
            except Exception:
                # never blow up the host thread
                pass
            # Wait with small granularity to be responsive to stop
            waited = 0.0
            while waited < self.interval and not self._stop_evt.is_set():
                time.sleep(min(0.1, self.interval - waited))
                waited += 0.1

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        # thread may still run briefly; no further action needed


__all__ = ["USSMonitor"]
