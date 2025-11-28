# Pipelines Directory Policy

This file explains the intended responsibilities and layout for the `pipelines/`
directory.

## Purpose

- `pipelines/` contains core, testable processing logic: reprojection, tile
  generation, Terrarium encoding, MBTiles streaming writer, and related
  utilities. Implementations here are intended to be importable and reusable
  from other scripts and unit tests.

## Guidelines

- Keep CLI entrypoints thin: provide `main()` wrappers that call library
  functions. Prefer exposing generator or function APIs (e.g.
  `generate_aggregated_tiles(...)`) rather than doing heavy work at module
  import time.
- Place small local shims here (for example, a Pillow-backed
  `imagecodecs.py`) if they support tests or scripts in the repo.
- Do not put one-off analysis scripts here; those belong under `scripts/`.

## `scripts/` vs `pipelines/`

- `pipelines/`: core implementation, importable functions, unit-testable.
- `scripts/`: user-facing or developer-facing thin CLI tools that import from
  `pipelines/` (examples: `scripts/inspect_tile_fill.py`).

If you are unsure where to put a file, prefer `pipelines/` for code that will
be reused or tested, and `scripts/` for ephemeral utilities and one-off test
wrappers.
