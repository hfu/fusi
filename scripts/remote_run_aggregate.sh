#!/usr/bin/env bash
# Remote runner helper for slate: run an aggregate on the remote host using all available memory
# Usage (from aalto):
#   ./scripts/remote_run_aggregate.sh --remote hfu@slate.local --source dem1a --output /tmp/output.dm
# The script will SSH to the remote host and run a conservative command sequence. It assumes
# the repository is available on the remote at the same path `/Users/hfu/github/fusi`.

set -euo pipefail

REMOTE=""
SOURCE=""
OUTPUT="output/remote_test.pmtiles"
KEEP_INTERMEDIATES=0
TMPDIR_OVERRIDE=""

usage(){
  cat <<'USAGE'
Usage: remote_run_aggregate.sh --remote user@host [--source name] [--output path] [--keep-intermediates]

This helper runs `just aggregate-split` on the remote host under the assumption that
the repo is at /Users/hfu/github/fusi on the remote. It does not copy keys or change
remote SSH config; set up public-key auth beforehand.
USAGE
}

USE_TMUX=0
SESSION_NAME=""
LOG_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="$2"; shift 2;;
    --tmpdir) TMPDIR_OVERRIDE="$2"; shift 2;;
    --source) SOURCE="$2"; shift 2;;
    --output) OUTPUT="$2"; shift 2;;
    --keep-intermediates) KEEP_INTERMEDIATES=1; shift;;
    --tmux) USE_TMUX=1; shift;;
    --session-name) SESSION_NAME="$2"; shift 2;;
    --log) LOG_PATH="$2"; shift 2;;
    --help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

if [[ -z "$REMOTE" ]]; then
  echo "--remote is required" >&2
  usage
  exit 2
fi

if [[ -z "$SOURCE" ]]; then
  echo "--source is required" >&2
  usage
  exit 2
fi

# Commands to run on remote. Adjust TMPDIR to use remote disk with space.
REMOTE_BASE_CMD=$(cat <<-'EOS'
set -euo pipefail
cd /Users/hfu/github/fusi
# If TMPDIR_OVERRIDE is provided in the remote environment, use it; otherwise
# default TMPDIR to the repo output directory on the remote host.
if [ -n "${TMPDIR_OVERRIDE:-}" ]; then
  export TMPDIR="${TMPDIR_OVERRIDE}"
else
  mkdir -p output || true
  export TMPDIR="$(pwd)/output"
fi
# activate pipenv if present, otherwise rely on system python
if [ -f Pipfile ]; then
  CMD_PREFIX="pipenv run"
else
  CMD_PREFIX=""
fi
AGG_CMD="$CMD_PREFIX just aggregate-split --keep-intermediates --overwrite '$SOURCE'"
echo "$AGG_CMD"
exec bash -lc "$AGG_CMD"
EOS
)

# If tmux requested, wrap the command to run in a detached tmux session and log output
if [[ "$USE_TMUX" -eq 1 ]]; then
  # default log path if not provided
  if [[ -z "$LOG_PATH" ]]; then
    LOG_PATH="/Users/hfu/github/fusi/output/${SESSION_NAME}.log"
  fi

  REMOTE_CMD=$(cat <<- TMUXCMD
set -euo pipefail
cd /Users/hfu/github/fusi || exit 2
# create output dir if needed
mkdir -p output
# find tmux binary
TMUX_BIN="$(command -v tmux || echo /opt/homebrew/bin/tmux)"
if [ ! -x "$TMUX_BIN" ]; then
  echo "tmux not found at $TMUX_BIN" >&2
  exit 3
fi
# Auto-detect existing session: if exactly one session exists, reuse it.
EXISTING_SESSIONS=$($TMUX_BIN ls 2>/dev/null | wc -l || echo 0)
if [ "$EXISTING_SESSIONS" -eq 1 ] && [ -z "${SESSION_NAME}" ]; then
  DETECTED=$($TMUX_BIN ls 2>/dev/null | awk -F: 'NR==1{print $1}')
  SESSION_NAME="$DETECTED"
fi
# If no session name yet, create a timestamped default
if [ -z "${SESSION_NAME}" ]; then
  SESSION_NAME="fusi_run_$(date +%Y%m%d%H%M%S)"
fi

# start detached tmux session that runs the aggregate and tees output to log
$TMUX_BIN new -d -s ${SESSION_NAME} "bash -lc '${REMOTE_BASE_CMD//\$SOURCE/$SOURCE} 2>&1 | tee ${LOG_PATH}'"
echo "Started tmux session: ${SESSION_NAME}, log: ${LOG_PATH}"
$TMUX_BIN ls || true
TMUXCMD
  )
else
  REMOTE_CMD="$REMOTE_BASE_CMD"
fi

echo "About to run aggregate on remote: $REMOTE"
echo "Remote command:" 
echo "$REMOTE_CMD"

read -p "Proceed to run on remote (you will be asked for SSH password/passphrase if no key)? [y/N] " ans
if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
  echo "Aborted by user"
  exit 0
fi

if [ -n "$TMPDIR_OVERRIDE" ]; then
  # Pass TMPDIR_OVERRIDE into the remote environment so REMOTE_BASE_CMD picks it up
  ssh "$REMOTE" TMPDIR_OVERRIDE="$TMPDIR_OVERRIDE" bash -lc "$REMOTE_CMD"
else
  ssh "$REMOTE" bash -lc "$REMOTE_CMD"
fi

echo "Remote run finished. Check remote output path or transfer results back as needed."
