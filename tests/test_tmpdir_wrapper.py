import subprocess
import tempfile
import os
from pathlib import Path


def test_start_aggregate_with_env_tmpdir_override(tmp_path):
    """Verify that start_aggregate_with_env.sh honors --tmpdir and writes log mentioning it."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    # create a simple command that writes a marker file
    cmd = "echo hello"

    script = Path("scripts/start_aggregate_with_env.sh")
    assert script.exists(), "start_aggregate_with_env.sh missing"

    # Run the wrapper with a TMPDIR override
    tmp_override = tmp_path / "tmpdir"
    tmp_override.mkdir()

    proc = subprocess.run(
        [str(script), "--workdir", str(workdir), "--tmpdir", str(tmp_override), "--cmd", cmd],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # The wrapper prints the starting env line; ensure the TMPDIR path appears
    out = proc.stdout
    assert str(tmp_override) in out


def test_safe_aggregate_accepts_tmpdir_flag(tmp_path):
    """Ensure safe_aggregate.sh accepts --tmpdir and sets TMPDIR accordingly (no run)."""
    script = Path("scripts/safe_aggregate.sh")
    assert script.exists()

    tmp_override = tmp_path / "tmpdir2"
    tmp_override.mkdir()

    # Run the script with --tmpdir and with a dummy source; script will attempt to run just,
    # but we only want to verify the environment selection logic before executing heavy work.
    # Run the script but make it exit early by passing a non-existent source and capturing output.
    proc = subprocess.run(
        [str(script), "--tmpdir", str(tmp_override), "dummy_source"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # The script should have exported TMPDIR; ensure the wrapper printed which TMPDIR it will use
    out = proc.stdout
    assert str(tmp_override) in out or "Using TMPDIR override" in out
