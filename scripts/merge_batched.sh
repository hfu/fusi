#!/usr/bin/env bash
set -euo pipefail
# Resumable, batched MBTiles merge
# Usage: ./scripts/merge_batched.sh DEST_MBtiles [BATCH_SIZE] [SRC_GLOB] [RESUME_DIR]
# Example: ./scripts/merge_batched.sh /Users/hfu/github/fusi/output/fusi.mbtiles 10000 '/Users/hfu/github/fusi/output/fusi_z*.mbtiles' /tmp/fusi_merge_resume

DEST=${1:-/Users/hfu/github/fusi/output/fusi.mbtiles}
BATCH=${2:-10000}
SRC_GLOB=${3:-/Users/hfu/github/fusi/output/fusi_z*.mbtiles}
RESUME_DIR=${4:-/tmp/fusi_merge_resume}
mkdir -p "$RESUME_DIR"

echo "[merge_batched] Destination: $DEST"
echo "[merge_batched] Batch size: $BATCH"
echo "[merge_batched] Sources glob: $SRC_GLOB"
echo "[merge_batched] Resume dir: $RESUME_DIR"

shopt -s nullglob
for SRC in $SRC_GLOB; do
    # Skip if same as DEST
    if [ "$(realpath "$SRC")" = "$(realpath "$DEST")" ]; then
        continue
    fi
    srcbase=$(basename "$SRC")
    echo "[merge_batched] Processing source: $srcbase"

    # list zooms
    zooms=$(sqlite3 "$SRC" "SELECT DISTINCT zoom_level FROM tiles ORDER BY zoom_level;" 2>/dev/null || true)
    for z in $zooms; do
        echo "[merge_batched]   Zoom: $z"
        resume_file="$RESUME_DIR/${srcbase}.z${z}.last"
        last_rowid=0
        if [ -f "$resume_file" ]; then
            last_rowid=$(cat "$resume_file" 2>/dev/null || echo 0)
        fi

        while true; do
            echo "[merge_batched]    last_rowid=$last_rowid -> inserting up to $BATCH rows"
            sqlite3 "$SRC" <<SQL || true
PRAGMA journal_mode=WAL;
ATTACH DATABASE '$DEST' AS dst;
BEGIN;
INSERT OR IGNORE INTO dst.tiles(zoom_level,tile_column,tile_row,tile_data)
SELECT zoom_level,tile_column,tile_row,tile_data
FROM tiles
WHERE zoom_level=$z AND rowid>$last_rowid
ORDER BY rowid
LIMIT $BATCH;
COMMIT;
DETACH DATABASE dst;
SQL

            new_last_rowid=$(sqlite3 "$SRC" "SELECT coalesce(max(rowid),$last_rowid) FROM tiles WHERE zoom_level=$z AND rowid>$last_rowid;" 2>/dev/null || echo "$last_rowid")
            if [ -z "$new_last_rowid" ]; then
                new_last_rowid=$last_rowid
            fi

            echo "$new_last_rowid" > "$resume_file"

            if [ "$new_last_rowid" -le "$last_rowid" ]; then
                echo "[merge_batched]    done zoom $z"
                break
            fi

            last_rowid=$new_last_rowid
            sleep 0.1
        done
    done
done

echo "[merge_batched] Merge complete"
