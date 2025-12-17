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
