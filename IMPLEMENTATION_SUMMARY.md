# Implementation Summary — fusi (Mapterhorn-style Terrain Pipeline)

This document summarizes the recent refactors, fixes, and operational
guidance for running `fusi` reliably on constrained machines (macOS `slate`,
external SSDs, ~16 GiB RAM). It describes the MBTiles-first design, memory and
TMPDIR mitigations, the new pixel-wise hybrid flow, and the monitoring helpers
added to support long unattended runs.

## High-level design

- MBTiles-first pipeline: raster tiles are streamed into an intermediate
  `.mbtiles` (SQLite) file and then packed into a PMTiles archive. This
  reduces peak memory and allows using `pmtiles convert` (go CLI) for the
  high-performance pack step.
- Zoom-splitting / spawn-per-group: large jobs can be subdivided by zoom
  ranges and run in subprocess groups to limit per-process memory pressure.
- Pixel-wise merging (new): a PMTiles writer that merges per-pixel from
  multiple MBTiles inputs, and a hybrid wrapper that generates per-source
  MBTiles sequentially then merges them to PMTiles — avoiding long-lived
  storage blowup when there are many sources.

## Recent fixes and changes (summary)

- TMPDIR hardening: `just` recipes and PMTiles wrapper ensure `TMPDIR` is set
  to a directory on the output volume by default, preventing ENOSPC on the
  system volume.
- Memory reduction:
  - `SourceRecord` simplified to a light NamedTuple to reduce per-record
    overhead.
  - Parent process defers building large in-memory lists when `spawn-per-group`
    is used.
  - `pipelines/mbtiles_writer.py` default `batch_size` reduced and checkpoint
    intervals exposed via environment variables.
- Watchdog: worker-level watchdog options (`--watchdog-memory-mb` /
  `--watchdog-time-seconds`) were added and forwarded by split orchestration.
- Pixel-wise PMTiles merger: `pipelines/merge_pmtiles_pixelwise.py` merges
  MBTiles inputs directly into PMTiles (priority/default or `max` mode).
- Hybrid wrapper script: `scripts/pixelwise_hybrid.sh` and a `just` recipe
  (`just pixel-wise`) perform sequential per-source MBTiles generation and
  then a pixel-wise merge to PMTiles to avoid holding many MBTiles at once.
- Monitoring helper: `scripts/monitor_run.sh` to sample RSS/USS, iostat and
  write logs for post-mortem analysis.

## Key files (what to look at)

- `pipelines/aggregate_pmtiles.py`: core aggregator; emits MBTiles and optional
  lineage MBTiles. TMPDIR is passed through to packers/children.
- `pipelines/mbtiles_writer.py`: streaming MBTiles writer with WAL control and
  environment-configurable checkpointing/commit sleeps.
- `pipelines/merge_pmtiles_pixelwise.py`: pixel-wise PMTiles output by merging
  multiple MBTiles inputs tile-by-tile.
- `pipelines/split_aggregate.py`: orchestrates split-by-zoom runs, forwards
  watchdog and TMPDIR settings to worker subprocesses.
- `scripts/pixelwise_hybrid.sh`: sequential per-source MBTiles generation
  followed by pixel-wise PMTiles merge; supports `--keep-intermediates`.
- `scripts/monitor_run.sh`: periodic sampling of system/process metrics.
- `justfile`: recipes were updated to set `TMPDIR` to `output/` by default and
  to expose the pixel-wise hybrid flow.

## Operational guidance (short)

- Always run on a volume with free space and set `TMPDIR` explicitly to a
  directory on that volume. Example (zsh):

  TMPDIR="$PWD/output"; mkdir -p "$TMPDIR"; chmod 700 "$TMPDIR"

- Example conservative env for macOS slate (16 GiB RAM):

  TMPDIR="$PWD/output" GDAL_CACHEMAX=256 \
    FUSI_MB_BATCH_SLEEP_SEC=0.02 FUSI_MB_COMMIT_SLEEP_SEC=0.10 \
    pipenv run python -u -m pipelines.split_aggregate \
    --watchdog-memory-mb 10240 dem1a dem10b

- If workers are being SIGKILL'd by a local watchdog, either raise
  `--watchdog-memory-mb` or reduce the number of sources per worker. The
  hybrid pixel-wise flow helps avoid large concurrent MBTiles sets.

## Pixel-wise hybrid flow (recommended when many sources)

1. For each source, sequentially run the aggregator to produce a per-source
   MBTiles (small lifetime on disk).
2. After per-source MBTiles are produced, run the pixel-wise PMTiles merger to
   produce the final `output/fusi.pmtiles` (optionally delete intermediates).

Use the `just pixel-wise <source...>` recipe to run this wrapper.

## Monitoring and troubleshooting

- Run `scripts/monitor_run.sh` in parallel to gather `ps`/USS/iostat samples.
- If you see a worker RSS/USS above the configured watchdog limit, reduce the
  per-worker workload, lower `GDAL_CACHEMAX`, reduce `warp-threads`, or
  increase `--watchdog-memory-mb`.
- If you hit `ENOSPC` during `pmtiles convert`, confirm `TMPDIR` is on the
  output volume and that `pmtiles` was started with `--tmpdir` pointing at
  that location.

## Testing and validation

- Unit tests cover parts of bounds generation and encoding; full `pytest`
  requires native deps (e.g. `rasterio`) present in the environment.
- Before full runs, perform a small smoke test (single source or small bbox)
  and convert via `pmtiles convert` to confirm packing behavior.

## Next steps and extensions (if problems persist)

- Implement streaming on-disk source indices (reduce initial record load).
- Add on-disk tile candidate indexing to avoid large in-memory lists.
- Further tune MBTiles writer batch sizes or use multiple sequential writers
  per subgroup when memory remains high.

---

If you want, I can:
- run a quick sweep through the repo and fix any remaining CLI arg forwarding
  or doc mismatches, or
- prepare a short shell snippet showing how to run `just pixel-wise` with the
  conservative recommended environment variables for `slate`.

Contact: repository maintainer (see `README.md`) for further operational
questions or to share monitor logs for analysis.
# Implementation Summary: Mapterhorn-Style Terrain Pipeline

## Overview

`fusi` is refactored into a robust two-stage pipeline that streams Terrarium
tiles into an intermediate MBTiles (SQLite) file and then packs the MBTiles
into a PMTiles archive. The intent is to reduce peak memory and temporary
spool pressure while remaining reliable on constrained external disks.

## Key Components

- `pipelines/aggregate_pmtiles.py`: multi-source aggregator (reproject,
  mosaic by priority, Terrarium encode, stream into MBTiles).
- `pipelines/mbtiles_writer.py`: streaming MBTiles writer using WAL with
  periodic `PRAGMA wal_checkpoint(TRUNCATE)` and a safe finalize sequence.
- `pipelines/convert_terrarium.py`: Terrarium encoding helpers and quantizer.
- `scripts/inspect_tile_fill.py`: inspection tool to compare MBTiles tiles to
  per-source assembled tiles for validation (uses an `imagecodecs` shim).

## Design Principles

- MBTiles-first: write tiles to `.mbtiles` incrementally, then run
  `pmtiles convert` (external CLI) to produce the final PMTiles archive.
- NaN-preserving reprojection: use `dst_nodata=np.nan` so that the merge step
  only fills pixels that are missing in higher-priority sources.
- Terrarium nodata policy: remaining NaN pixels are encoded as 0 m in the
  final Terrarium tile payload.

## Terrarium Encoding (short)

Decoding formula:

```text
elevation = (R × 256 + G + B / 256) - 32768
```

Encoding uses zoom-dependent quantization (mapterhorn-style) before packing
into lossless WebP.

## Operational Notes

- Always set `TMPDIR` to the output volume (for example, `TMPDIR="$PWD/output"`) to
  avoid filling the system volume during long runs.
- Recommended runtime flags for stability: `GDAL_CACHEMAX=512`,
  `--warp-threads 1`, `--io-sleep-ms 1`, and `--progress-interval 100`.
- Manual WAL checkpoint (if interrupted):

```bash
sqlite3 output/foo.mbtiles "PRAGMA wal_checkpoint(TRUNCATE); PRAGMA journal_mode=DELETE;"
```

## Testing / Validation

- Unit tests: bounds generation, encoding round-trip
- Smoke tests: MBTiles → PMTiles via `pmtiles convert` on small fixtures
- Runtime checks: monitor `output/*.mbtiles` and their `.wal/.shm` files

## Notes on Tooling

- `rio-rgbify` has been removed.
- The pipeline logic is implemented in Python; for final packing we prefer
  the `pmtiles convert` CLI for performance. A Python `pmtiles.writer` helper
  exists as an optional fallback for environments without the CLI.

## References

- mapterhorn: https://github.com/mapterhorn/mapterhorn
- Terrarium encoding: https://github.com/tilezen/joerd/blob/master/docs/formats.md#terrarium
- PMTiles: https://github.com/protomaps/PMTiles
```markdown
# Implementation Summary: Mapterhorn-Style Terrain Pipeline

## Overview

Refactored `fusi` into a robust, mapterhorn-compatible two-stage pipeline that
streams Terrarium tiles into an intermediate MBTiles SQLite file and then packs
the resulting MBTiles into a PMTiles archive using the `pmtiles convert` CLI.
This `MBTiles`-first approach reduces peak memory / temp-spool pressure and
improves reliability on constrained disks (for example, external SSDs).
*** Begin Clean Implementation Summary

# Implementation Summary — fusi (Mapterhorn-style Terrain Pipeline)

`fusi` is a two-stage pipeline: it streams Terrarium tiles into an
intermediate MBTiles (SQLite) file and then packs that MBTiles into a
PMTiles archive (preferably using the `pmtiles convert` CLI).

This MBTiles-first approach reduces peak memory and temp-spool pressure and
improves reliability when running long jobs on external disks.

## Key components

- `pipelines/aggregate_pmtiles.py` — multi-source aggregator: reprojection,
  priority-based mosaicking, Terrarium encoding (lossless WebP), and streaming
  tiles into MBTiles. It optionally emits lineage MBTiles.
- `pipelines/mbtiles_writer.py` — streaming MBTiles writer using WAL mode with
  periodic `PRAGMA wal_checkpoint(TRUNCATE)` and a safe finalize sequence that
  reverts to `journal_mode=DELETE`.
- `pipelines/mbtiles_to_pmtiles.py` — a small Python fallback writer for
  environments without the `pmtiles` CLI.
- `scripts/pmtiles_wrapper.sh` — wrapper that ensures temporary files are
  written on the chosen volume and invokes `pmtiles convert` (or the Python
  fallback).

## Operational notes (concise)

- Always set `TMPDIR` to a directory on the output volume (for example
  `TMPDIR="$PWD/output"`) or pass an explicit tmpdir to the wrapper. This
  prevents exhausting the system temp area during long runs.
- Recommended defaults for stability: `GDAL_CACHEMAX=512`, `--warp-threads 1`,
  `--io-sleep-ms 1`, and a reasonable `--progress-interval`.
- The `justfile` tasks `aggregate` and `aggregate-split` already export
  `TMPDIR` to `output/` by default; the `pmtiles` wrapper also exports and
  passes `--tmpdir` to the `pmtiles convert` CLI.

## Encoding summary

- Terrarium decoding: `elevation = (R * 256 + G + B/256) - 32768`.
- Implementation uses zoom-dependent vertical quantization (mapterhorn-style)
  before packing into lossless WebP to reduce size while preserving useful
  elevation precision.

## Testing and validation

- Unit tests cover bounds generation and encoding round-trips.
- Small smoke tests (MBTiles → PMTiles) are recommended before full runs.
- After conversion run: `pmtiles verify output/fusi.pmtiles` and inspect
  metadata with `pmtiles show --metadata`.

## Fallbacks and tooling

- Preferred packing: `pmtiles convert` (go-pmtiles). If not available the
  code falls back to a Python writer in `pipelines/mbtiles_to_pmtiles.py`.
- `scripts/pmtiles_wrapper.sh` now exports `TMPDIR` and passes `--tmpdir` to
  `pmtiles convert` for defensive, portable behavior.

*** End Clean Implementation Summary
