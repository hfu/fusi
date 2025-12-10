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


def get_uss_bytes() -> int:
    """Return best-effort unique set size (USS) in bytes for this process.

    If `psutil` supports `memory_full_info().uss` it will be used. If not
    available, falls back to RSS via `get_rss_bytes()`.
    """
    if psutil is not None:
        try:
            proc = psutil.Process(os.getpid())
            try:
                mfi = proc.memory_full_info()
                uss = getattr(mfi, "uss", None)
                if uss:
                    return int(uss)
            except Exception:
                # memory_full_info may not be available on some platforms
                pass
            # Fall back to summing process + children rss if possible
            try:
                total = proc.memory_info().rss
                for child in proc.children(recursive=True):
                    try:
                        total += child.memory_info().rss
                    except Exception:
                        continue
                return int(total)
            except Exception:
                return int(get_rss_bytes())
        except Exception:
            return int(get_rss_bytes())

    # No psutil -> rss fallback
    return int(get_rss_bytes())


def format_bytes(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0:
            return f"{num:3.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}PB"
