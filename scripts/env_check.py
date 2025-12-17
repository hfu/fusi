#!/usr/bin/env python3
"""Environment check for fusi production run.

Checks:
- Python executable and version
- `pmtiles` Python package importable and version
- `pmtiles` CLI availability
- `sqlite3` CLI availability
- ability to write a small temp file to the output directory

Run: python3 scripts/env_check.py [output_dir]
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile


def ok(msg: str) -> None:
    print("[OK] ", msg)


def warn(msg: str) -> None:
    print("[WARN]", msg)


def fail(msg: str) -> None:
    print("[FAIL]", msg)


def main(argv: list[str]) -> int:
    out_dir = argv[1] if len(argv) > 1 else "/Users/hfu/github/fusi/output"
    print("fusi env check")
    print("output_dir:", out_dir)

    # Python executable and version
    print("\nChecking Python...")
    try:
        py = sys.executable
        ver = sys.version.splitlines()[0]
        ok(f"Python executable: {py} ({ver})")
    except Exception as e:
        fail(f"Python check failed: {e}")
        return 2

    # pmtiles Python package
    print("\nChecking pmtiles Python package...")
    try:
        import pmtiles  # type: ignore

        ver = getattr(pmtiles, "__version__", None)
        if ver:
            ok(f"pmtiles package importable, version={ver}")
        else:
            ok("pmtiles package importable")
    except Exception as e:
        warn(f"pmtiles Python package not importable: {e}. Python fallback will fail without it.")

    # pmtiles CLI
    print("\nChecking pmtiles CLI (go-pmtiles)...")
    pm_cli = shutil.which("pmtiles")
    if pm_cli:
        ok(f"pmtiles CLI found: {pm_cli}")
    else:
        warn("pmtiles CLI not found in PATH. Using Python writer as fallback may be slower and requires pmtiles Python package.")

    # sqlite3 CLI
    print("\nChecking sqlite3 CLI...")
    sqlite_cli = shutil.which("sqlite3")
    if sqlite_cli:
        ok(f"sqlite3 CLI found: {sqlite_cli}")
    else:
        warn("sqlite3 CLI not found in PATH; some helper scripts assume sqlite3 command-line tool.")

    # Output dir write test
    print("\nChecking output directory writeability and free space...")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        fail(f"Cannot create output directory {out_dir}: {e}")
        return 2

    # Try to create a small temp file in the output directory
    try:
        with tempfile.NamedTemporaryFile(prefix="fusi_envcheck_", dir=out_dir, delete=False) as f:
            f.write(b"envcheck")
            tmpname = f.name
        ok(f"Wrote temp file: {tmpname}")
        try:
            os.remove(tmpname)
            ok(f"Removed temp file: {tmpname}")
        except Exception as e:
            warn(f"Could not remove temp file {tmpname}: {e}")
    except Exception as e:
        fail(f"Failed to write temp file to {out_dir}: {e}")
        return 2

    # Check disk free space for the mount containing out_dir
    try:
        stat = shutil.disk_usage(out_dir)
        free_gib = stat.free / (1024 ** 3)
        ok(f"Free space on {out_dir}: {free_gib:.1f} GiB")
    except Exception as e:
        warn(f"Could not determine free space for {out_dir}: {e}")

    print("\nEnvironment check complete. Address any WARN/FAIL messages before long runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
