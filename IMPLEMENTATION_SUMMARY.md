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

## Changes Made

### Core pipeline scripts (in `pipelines/`)

- `source_bounds.py`: extracts GeoTIFF metadata and writes `bounds.csv` for a
  source-store.
- `convert_terrarium.py`: single-file GeoTIFF → Terrarium PMTiles helper.
- `aggregate_pmtiles.py`: multi-source aggregator that reprojects, mosaics by
  priority, encodes Terrarium tiles (lossless WebP), streams into MBTiles, and
  delegates final packing to `pmtiles convert`.
- `mbtiles_writer.py`: streaming MBTiles writer using SQLite WAL with periodic
  `wal_checkpoint(TRUNCATE)` and a safe finalize that reverts to
  `journal_mode=DELETE`.
- `verify_mbtiles_yflip.py`: helper to validate TMS⇄XYZ handling and payload
  equality for a sample bounding box.

### Project layout and tooling

- `justfile`: updated to set `TMPDIR` to the output directory by default,
  forward options into the Python aggregator, and invoke `pmtiles convert` if
  available.
- Dependencies: moved away from `rio-rgbify`; core Python deps include
  `rasterio`, `numpy`, `mercantile`, `imagecodecs` (or a small Pillow-backed
  shim), and `pmtiles` (optional Python writer).

## Key Design Decisions

- MBTiles-first: stream tiles into an `.mbtiles` file (SQLite) to avoid in-
  process large spool/memory pressure; then call `pmtiles convert` to produce
  a compact PMTiles archive.
- NaN-preserving reproject + priority-fill: during reprojection we use
  `dst_nodata=np.nan` so that the mosaic step can fill only pixels that are
  missing (NaN) in higher-priority sources from lower-priority sources.
- Terrarium encoding: final encoding converts remaining NaN → 0 m so viewers
  see nodata as 0 m per project policy.

## Terrarium Encoding (summary)

Finer details are implemented in `pipelines/convert_terrarium.py` but the
encoding/decoding formulas are:

```text
decoding: elevation = (R × 256 + G + B / 256) - 32768
```

When producing tiles we quantize elevation to a zoom-dependent vertical
resolution (mapterhorn formula) before encoding.

## Vertical Resolution by Zoom (example)

| Zoom | Resolution | Pixel Size |
|------|-----------:|-----------:|
| 0    | 2048 m     | 78.3 km    |
| 10   | 2 m        | 76.4 m     |
| 15   | 0.0625 m   | 2.39 m     |
# Implementation Summary: Mapterhorn-Style Terrain Pipeline

## Overview

Refactored `fusi` into a robust, mapterhorn-compatible two-stage pipeline that
streams Terrarium tiles into an intermediate MBTiles SQLite file and then
packs the resulting MBTiles into a PMTiles archive using the `pmtiles convert`
CLI. This MBTiles-first approach reduces peak memory / temp-spool pressure and
improves reliability on constrained disks (for example, external SSDs).

## Changes Made

### Core pipeline scripts (in `pipelines/`)

- `source_bounds.py`: extracts GeoTIFF metadata and writes `bounds.csv` for a
  source-store.
- `convert_terrarium.py`: single-file GeoTIFF → Terrarium PMTiles helper.
- `aggregate_pmtiles.py`: multi-source aggregator that reprojects, mosaics by
  priority, encodes Terrarium tiles (lossless WebP), streams into MBTiles,
  and delegates final packing to `pmtiles convert`.
- `mbtiles_writer.py`: streaming MBTiles writer using SQLite WAL with periodic
  `wal_checkpoint(TRUNCATE)` and a safe finalize that reverts to
  `journal_mode=DELETE`.
- `verify_mbtiles_yflip.py`: helper to validate TMS⇄XYZ handling and payload
  equality for a sample bounding box.

### Project layout and tooling

- `justfile`: updated to set `TMPDIR` to the output directory by default,
  forward options into the Python aggregator, and invoke `pmtiles convert` if
  available.
- Dependencies: moved away from `rio-rgbify`; core Python deps include
  `rasterio`, `numpy`, `mercantile`, `imagecodecs` (or a small Pillow-backed
  shim), and `pmtiles` (optional Python writer).

## Key Design Decisions

- MBTiles-first: stream tiles into an `.mbtiles` file (SQLite) to avoid in-
  process large spool/memory pressure; then call `pmtiles convert` to produce
  a compact PMTiles archive.
- NaN-preserving reproject + priority-fill: during reprojection we use
  `dst_nodata=np.nan` so that the mosaic step can fill only pixels that are
  missing (NaN) in higher-priority sources from lower-priority sources.
- Terrarium encoding: final encoding converts remaining NaN → 0 m so viewers
  see nodata as 0 m per project policy.

## Terrarium Encoding (summary)

Finer details are implemented in `pipelines/convert_terrarium.py` but the
encoding/decoding formulas are:

```text
decoding: elevation = (R × 256 + G + B / 256) - 32768
```

When producing tiles we quantize elevation to a zoom-dependent vertical
resolution (mapterhorn formula) before encoding.

## Vertical Resolution by Zoom (example)

| Zoom | Resolution | Pixel Size |
|------|-----------:|-----------:|
| 0    | 2048 m     | 78.3 km    |
| 10   | 2 m        | 76.4 m     |
| 15   | 0.0625 m   | 2.39 m     |
| 19   | 0.0039 m   | 0.149 m    |

## Advantages Over Previous Implementation

1. **Reduced external tool reliance**: removed `rio-rgbify` dependency. The
   pipeline still uses the `pmtiles convert` CLI for performant PMTiles packing
   (recommended). A pure-Python `pmtiles.writer` helper is available as an
   optional fallback.
2. **Mapterhorn compatible**: tile encoding and metadata follow mapterhorn
   conventions.
3. **Zoom-dependent vertical quantization**: reduces output size while
   preserving useful elevation precision.
4. **Lossless WebP**: tile payloads are encoded losslessly to preserve data.
5. **Robust MBTiles writer**: WAL mode with periodic checkpoints prevents
   `.wal` from growing unbounded during long writes and provides a safe
   finalize sequence.

## Testing

### Test Coverage
---
# Implementation Summary — fusi (Mapterhorn-style Terrain Pipeline)

このドキュメントは `fusi` の設計要旨、運用ポリシー、最近の変更点をまとめたものです。

## 概要

`fusi` は複数の標高 GeoTIFF を受け取り、Terrarium タイル（512×512、Lossless WebP）を生成して最終的に PMTiles に梱包するためのパイプラインです。主な方針は「MBTiles-first」：タイルをまずストリーミングで `.mbtiles`（SQLite）に書き込み、その後 `pmtiles convert`（外部 CLI）で PMTiles に変換します。

このアプローチにより、プロセス内のピークメモリや一時スプールを抑え、外付けディスク上での長時間処理に耐えられるようになります。

## 主なコンポーネント

- `pipelines/aggregate_pmtiles.py` — マルチソース集約器。再投影、優先度順マージ（上位の NaN を下位で埋める）、Terrarium エンコード、MBTiles へのストリーミング書き出し、（オプションで）系譜(lineage) MBTiles の生成を行う。
- `pipelines/mbtiles_writer.py` — WAL モードによるストリーミング書き出し。定期的に `PRAGMA wal_checkpoint(TRUNCATE)` を実行し、最終化時に `journal_mode=DELETE` に戻す実装。
- `pipelines/mbtiles_to_pmtiles.py` — Python フォールバックで MBTiles を PMTiles に変換する小さなライブラリ（`pmtiles` CLI が無い環境向け）。
- `pipelines/lineage.py` — 系譜（各ピクセルがどのソース由来か）を RGB にマップするプロトタイプ機能。
- `scripts/` 以下 — `pipelines/` の薄い CLI ラッパー群（検査用スクリプト等）。

## 運用上の重要点（推奨設定）

- `TMPDIR` は出力ボリュームに設定する（例: `TMPDIR="$PWD/output"`）。システムボリュームの ENOSPC を避けるため必須推奨。
- 環境: `GDAL_CACHEMAX=512`、`--warp-threads 1`、`--io-sleep-ms 1` を既定で使う。
- 既定では詳細ログ（verbose）が有効。出力がうるさい場合は `--silent` を指定して抑制可能。互換のため `--verbose` も受け付ける。
- `--emit-lineage` を指定すると、主 MBTiles 作成後に系譜 MBTiles を生成し、可能であれば自動で PMTiles に変換する（`--lineage-suffix` のデフォルトは `-lineage`）。
- PMTiles 変換は優先して `pmtiles` CLI（`go-pmtiles`）を使用し、無ければ `pipelines/mbtiles_to_pmtiles.py` の Python 実装にフォールバックする。

## 技術的方針

- 再投影時は nodata を NaN で扱い、マージ段階では上位ソースの値を優先し、上位が NaN の箇所のみ下位で埋める。
- 最終エンコードでは残存する NaN を 0 m（Terrarium の対応する RGB）として出力する。
- 系譜はピクセル毎にソース優先度インデックス（int16、-1 = nodata）として計算し、必要に応じて可視化用 RGB タイルを出力する。

## README と CLI の更新点（今回の変更）

- `--silent` を追加、既定で詳細ログ（verbose）を有効化。
- `aggregate_pmtiles.py` が MBTiles 作成後に自動で `pmtiles convert` を試行するようになった（CLI 優先、Python フォールバックあり）。
- `--emit-lineage` 実行時に系譜 MBTiles（basename + `-lineage`）を生成し、可能であれば系譜用 PMTiles も同時生成する。
- テスト用の小規模リージョン例は `iwaki`（いわき市）を推奨テスト対象として README に追記。

## 進捗ログと ETA について

- 進捗ログは「書き出し済みタイル数 / チェック済み候補数 / 全候補に対する割合」を出力します。
- ETA（残り時間）は候補数スキャン結果をもとに算出します。初期セットアップ（バケット構築など）時間が ETA を歪めないよう、セットアップ完了後にタイマを開始する改善を行いました。
- さらに精度を上げるには、初期 N タイル（例: 最初の 100–500 タイル）での実測速度をブートストラップして推定に用いる方法（ブートストラップ平均や指数移動平均）を導入することが考えられます。

## 推奨ワークフロー（例）

1. 小規模テスト（推奨: `iwaki`）で挙動確認:

```bash
mkdir -p output/iwaki
TMPDIR="$PWD/output/iwaki" GDAL_CACHEMAX=512 \
  just aggregate -o output/iwaki.pmtiles --bbox 140.55 36.80 141.15 37.40 --overwrite dem1a dem10b
```

2. 問題なければ本番範囲で `just aggregate` を実行（出力は MBTiles → PMTiles）:

```bash
TMPDIR="$PWD/output" GDAL_CACHEMAX=512 \
  just aggregate -o output/fusi.pmtiles dem1a dem10b --max-zoom 16 --progress-interval 100 --overwrite
```

3. 系譜を生成する場合は `--emit-lineage` を追加。出力は `output/<name>-lineage.mbtiles` と `output/<name>-lineage.pmtiles`（可能なら自動生成）。

## 今後の改善候補

- ETA 精度向上のためのブートストラップ平均 (初期 N タイル) の導入
- 系譜 MBTiles のメタデータ強化（`encoding: lineage` など）
- パレットの外部設定や系譜のデータタイル（可逆バイナリ）出力オプション

---

更新履歴: セッション内で `--silent`/verbose デフォルト、自動 PMTiles 変換、`--emit-lineage` の PMTiles 自動変換、README の `iwaki` 推奨を追加・コミット済み。
