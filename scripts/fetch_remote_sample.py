#!/usr/bin/env python3
"""Fetch a small sample of source-store from a remote host for smoke tests.

This is a conservative helper: it does not run any aggregation itself. It
supports two safe modes:

- `--check` : verify SSH connectivity and existence of the remote path.
- `--rsync-sample` : use `rsync` to copy a small subset (pattern-based) into
  a local temporary directory for further testing.

Usage examples:
  # Check remote path
  ./scripts/fetch_remote_sample.py --remote hfu@slate.local:/Users/hfu/github/fusi/source-store --check

  # Rsync sample *.tif files to ./tmp/sample
  ./scripts/fetch_remote_sample.py --remote hfu@slate.local:/Users/hfu/github/fusi/source-store \
      --rsync-sample --pattern "*.tif" --dest tmp/sample

Notes:
 - This script assumes `ssh` and `rsync` are available on the machine running it.
 - It is intentionally simple and conservative to avoid noisy IO on the remote host.
"""
from __future__ import annotations

import argparse
import subprocess
import shutil
from pathlib import Path
import sys


def check_ssh_path(remote: str) -> int:
    """Return ssh exit code for a simple test: `ssh host test -e path`.

    remote: user@host:/absolute/path
    """
    if ":" not in remote:
        print("Remote should be in the form user@host:/absolute/path")
        return 2

    userhost, path = remote.split(":", 1)
    cmd = ["ssh", userhost, "test", "-e", path]
    return subprocess.call(cmd)


def rsync_sample(remote: str, pattern: str, dest: Path, dry_run: bool = False) -> int:
    """Use rsync to copy files matching `pattern` from remote path into dest.

    This uses rsync include/exclude rules to avoid copying everything.
    """
    if shutil.which("rsync") is None:
        print("Error: rsync not found on PATH")
        return 2

    if ":" not in remote:
        print("Remote should be in the form user@host:/absolute/path")
        return 2

    userhost, path = remote.split(":", 1)
    dest.mkdir(parents=True, exist_ok=True)

    include_rule = f"--include={pattern}"
    cmd = [
        "rsync",
        "-av",
        include_rule,
        "--exclude=*",
        f"{userhost}:{path}/",
        str(dest),
    ]

    if dry_run:
        print("Dry run: ", " ".join(cmd))
        return 0

    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch a small sample from remote source-store")
    p.add_argument("--remote", required=True, help="Remote path like user@host:/abs/path")
    p.add_argument("--check", action="store_true", help="Check remote path exists via ssh")
    p.add_argument("--rsync-sample", action="store_true", help="Rsync sample files matching pattern")
    p.add_argument("--pattern", default="*.tif", help="Include pattern for rsync (default: *.tif)")
    p.add_argument("--dest", default="tmp/sample", help="Destination local directory")
    p.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    args = p.parse_args()

    if args.check:
        rc = check_ssh_path(args.remote)
        if rc == 0:
            print("Remote path exists and is reachable")
            sys.exit(0)
        else:
            print("Remote path not found or ssh failed (exit code: %d)" % rc)
            sys.exit(rc)

    if args.rsync_sample:
        dest = Path(args.dest)
        rc = rsync_sample(args.remote, args.pattern, dest, dry_run=args.dry_run)
        if rc == 0:
            print(f"Sample copied to: {dest}")
        else:
            print(f"rsync failed with exit code: {rc}")
        sys.exit(rc)

    print("No action requested. Use --check or --rsync-sample.")


if __name__ == "__main__":
    main()
