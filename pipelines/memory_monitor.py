"""Small memory monitoring helper.

Provides a simple `get_rss_bytes()` function. Uses `psutil` if available,
otherwise falls back to `resource.getrusage` where possible.
"""
from __future__ import annotations

try:
    import psutil  # optional
except Exception:  # pragma: no cover - optional
    psutil = None

import os
import resource


def get_rss_bytes() -> int:
    """Return current process resident set size (RSS) in bytes.

    Uses psutil if available; otherwise falls back to resource.getrusage.
    """
    if psutil is not None:
        return int(psutil.Process(os.getpid()).memory_info().rss)

    # Fallback: resource.ru_maxrss is platform-dependent. On macOS it's bytes,
    # on Linux it's kilobytes. We'll attempt to detect and normalize.
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Heuristic: if usage looks small (<1e6) treat as KB (Linux), else bytes
    if usage < 1_000_000:
        return int(usage * 1024)
    return int(usage)


def format_bytes(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0:
            return f"{num:3.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}PB"
