"""Small terminal spinner utility and GC callback registration.

When garbage collection occurs frequently, printing a literal '.' for each
event floods logs. This module provides a compact spinner that writes
``"\r/ - \\ |"`` (rotating) to stdout and flushes, giving a visual
indication without producing many lines.

Usage:
    from pipelines.spinner import register_gc_spinner
    register_gc_spinner()  # hooks into gc.callbacks

The spinner is intentionally lightweight and optional; it only registers
the callback when requested.
"""
from __future__ import annotations

import gc
import os
import sys
import threading
import time
from typing import Iterable


class Spinner:
    """Simple spinning cursor that writes a single-character frame with '\r'.

    Call `spin_once()` to emit the next frame. The spinner does not emit a
    newline and leaves the cursor at the start of the line so subsequent
    log lines will overwrite it.
    """

    FRAMES: Iterable[str] = ("/", "-", "\\", "|")

    def __init__(self) -> None:
        self._idx = 0
        self._lock = threading.Lock()
        self._last_emit = 0.0
        # Minimum interval between visual updates in seconds to avoid
        # overwhelming the terminal when GC runs in tight bursts.
        self._min_interval = 0.05

    def spin_once(self) -> None:
        now = time.time()
        with self._lock:
            if now - self._last_emit < self._min_interval:
                return
            ch = tuple(self.FRAMES)[self._idx % len(tuple(self.FRAMES))]
            try:
                # Only emit visual updates to an interactive TTY unless the
                # caller explicitly forces spinner output via the
                # `FUSI_FORCE_SPINNER` env var. Writing spinner frames into
                # a logfile is noisy and can corrupt single-line log readers.
                force = os.environ.get("FUSI_FORCE_SPINNER", "")
                if sys.stdout.isatty() or force.lower() in ("1", "true", "yes"):
                    # Use \r to overwrite the current line and flush immediately.
                    sys.stdout.write("\r" + ch)
                    sys.stdout.flush()
            except Exception:
                # Never let the spinner crash the host process.
                pass
            self._idx += 1
            self._last_emit = now

    def clear(self) -> None:
        """Clear the spinner character (write carriage return + space)."""
        try:
            if sys.stdout.isatty() or os.environ.get("FUSI_FORCE_SPINNER", "").lower() in (
                "1",
                "true",
                "yes",
            ):
                sys.stdout.write("\r ")
                sys.stdout.flush()
        except Exception:
            pass


_GLOBAL_SPINNER: Spinner | None = None


def get_global_spinner() -> Spinner:
    global _GLOBAL_SPINNER
    if _GLOBAL_SPINNER is None:
        _GLOBAL_SPINNER = Spinner()
    return _GLOBAL_SPINNER


def _gc_callback(phase, info) -> None:  # pragma: no cover - tiny shim
    # Only react to 'stop' (collection finished). The `phase` value is a
    # string like 'start'/'stop' as per Python's gc.callbacks API.
    try:
        if phase == "stop":
            get_global_spinner().spin_once()
    except Exception:
        pass


def register_gc_spinner() -> None:
    """Register a GC callback that emits a spinner frame on each collection stop.

    Calling this multiple times is safe (the registration checks for an
    existing callback). This only installs a tiny visual effect and does not
    change GC behaviour.
    """
    # Defensive: don't register if gc.callbacks is not present
    cb_list = getattr(gc, "callbacks", None)
    if cb_list is None:
        return

    # If stdout is not a TTY and the user hasn't explicitly forced the
    # spinner with FUSI_FORCE_SPINNER, skip registering so we don't write
    # spinner frames into logfiles/redirected output.
    force = os.environ.get("FUSI_FORCE_SPINNER", "")
    if not (sys.stdout.isatty() or force.lower() in ("1", "true", "yes")):
        return

    # Avoid duplicate registration
    for cb in cb_list:
        if getattr(cb, "__name__", None) == _gc_callback.__name__:
            return

    try:
        gc.callbacks.append(_gc_callback)
    except Exception:
        # If callbacks append fails, silently ignore — spinner is optional.
        pass


__all__ = ["Spinner", "get_global_spinner", "register_gc_spinner"]
