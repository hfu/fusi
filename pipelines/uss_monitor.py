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

    def __init__(self, interval: float = 0.5) -> None:
        self.interval = float(interval)
        self._peak: int = 0
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

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
