# fusi

`fusi` は国土地理院の標高 GeoTIFF を Terrarium 形式のタイルに変換するツールチェーンです。mapterhorn が示した手法をベースに、Web Mercator（EPSG:3857）への自動再投影やズーム別の垂直解像度管理を備えています。内部的には Lossless WebP のタイルを MBTiles に書き出し、`go-pmtiles` の `pmtiles convert` コマンドで PMTiles に変換します。

## 主な特徴

- `bounds.csv` による GeoTIFF メタデータ管理と空間インデックス
- 512px タイルを前提にした自動ズーム推定（GSD から max zoom を決定）
- Terrarium エンコード（mapterhorn 互換）と nodata を 0 m に正規化する安全策
- Lossless WebP タイルを MBTiles にストリーミング書き込みし、その後 PMTiles に変換
- 集約パイプライン：複数 GeoTIFF をオンザフライでモザイクし 1 本の MBTiles/PMTiles に統合
- 進捗表示：候補タイル数・書き出しタイル数・割合を標準出力に逐次表示
- `just` コマンドで一連のタスクを自動化

## 必要なもの

- Python 3.12 以上
- pipenv
- just（Homebrew: `brew install just`）
- go-pmtiles （`pmtiles` CLI、例: `brew install golang && go install github.com/protomaps/go-pmtiles/cmd/pmtiles@latest`）

### 参考: ツールの導入例

```bash
brew install just parallel   # macOS
pip3 install --user pipenv
go install github.com/protomaps/go-pmtiles/cmd/pmtiles@latest
```

## セットアップ

```bash
git clone https://github.com/hfu/fusi.git
cd fusi
just setup          # pipenv install を実行
just check          # 実行に必要なツールを確認
```

## データの配置とプリセット

1. 標高 GeoTIFF を `source-store/<source_name>/` に格納します。ファイル名の規則は自由ですが、`bounds.csv` が参照できる位置にまとめておく必要があります。
2. 大規模データセットでは、シンボリックリンクでサブセットを作るとテストが容易です。

```bash
mkdir -p source-store/japan_dem
cp /path/to/*.tif source-store/japan_dem/

# 例: 全ファイルのシンボリックリンクを bulk_all にまとめる
python - <<'PY'
from pathlib import Path
src = Path('source-store/japan_dem')
dst = Path('source-store/bulk_all')
dst.mkdir(exist_ok=True)
for tif in sorted(src.glob('*.tif')):
    link = dst / tif.name
    if not link.exists():
        link.symlink_to(tif.resolve())
PY
```

## 基本ワークフロー

### 1. bounds.csv を生成

```bash
just bounds bulk_all
```

標準出力に処理件数が表示され、`source-store/bulk_all/bounds.csv` が生成されます。

### 2. MBTiles/PMTiles を生成（安全デフォルトでI/O安定化）

```bash
just aggregate bulk_all
```

- `output/fusi.pmtiles` が生成されます（内部的に `output/fusi.mbtiles` → `pmtiles convert`）。
  
  補足: MBTiles の書き込みでは SQLite の WAL モードを使用します。長時間・大規模書き込み時に WAL ファイルが肥大化しないよう、内部で定期的に `PRAGMA wal_checkpoint(TRUNCATE)` を実行して `.wal` を短く保ち、処理完了時に `PRAGMA journal_mode=DELETE` に戻して `.wal/.shm` を削除する設計になっています。
- 別名で出力したい場合は `just aggregate -o output/bulk_all.pmtiles bulk_all` のように `-o/--output` で PMTiles パスを指定します。
- `bounds.csv` から対象ファイルを抽出し、各タイルごとに再投影・モザイク・Terrarium エンコードを行います。
- 標準出力にはズーム別の候補タイル数と進捗率に加え、フェーズログ（union bounds / coarse bucket 構築 / 候補数計測）が表示され、停滞の切り分けが容易です。
- I/O 安定化のため、以下を既定で有効化しています（必要に応じて上書き可能です）。
  - `TMPDIR` を出力ディレクトリに設定（Python の一時ファイルを外付け側へ誘導）
  - `GDAL_CACHEMAX=512`（環境変数で変更可）
  - `--warp-threads 1`（再投影スレッドを1に抑制）
  - `--io-sleep-ms 1`（タイルごとに1msスリープでI/Oに負圧）
  - `--progress-interval 200`（進捗ログの既定間隔）
  - `--verbose`（詳細ログを既定有効）

オプション（`just aggregate` 経由で `pipelines/aggregate_pmtiles.py` に渡ります）

- `-o/--output <pmtiles>`: 最終的な PMTiles パスを指定（内部的に同名の `.mbtiles` が生成されます）
- `--bbox <west> <south> <east> <north>`: WGS84 度で出力範囲を限定
- `--min-zoom`, `--max-zoom`: 出力ズームレンジを明示指定
- `--progress-interval N`: 進捗ログの間隔を調整

### 3. 出力の確認

```bash
just inspect output/fusi.pmtiles
```

ヘッダ情報・ズームレンジ・バウンディングボックスなどが確認できます。

### 4. 配布先へのアップロード（任意）

```bash
just upload
```

`output/fusi.pmtiles` を想定したアップロードタスクです。宛先やファイル名を変える場合は `justfile` の `upload` レシピを調整してください。

## オプション: 単一 GeoTIFF の変換

一枚の GeoTIFF を手早く確認したいときは `just convert` を使えます。

```bash
just convert source-store/bulk_all/sample.tif output/sample.pmtiles
```

- `--max-zoom` を省略すると、ソースの Ground Sample Distance (GSD) からズームを自動推定します。
- 実行ログに「Auto-selected max zoom …」が表示されます。

## 実務で得た Tips

- **テストから本番へ**: 小さなサブセットで `just aggregate` を試し、ズーム自動推定や nodata=0 m の挙動を確認してから全量処理すると安全です。
- **進捗ログ**: 大量データのときは出力が数時間続くことがあります。進捗ログには「書き出し済みタイル数」「チェック済み候補数」「全候補に対する割合」が表示されるため、残り時間の目安になります。フェーズログ（union/bucket/count）で停滞箇所を切り分けできます。
- **一時ファイルの置き場**: 既定で出力ディレクトリ配下にスプールするため、macOS のシステムボリューム容量逼迫を避けられます。独自ディレクトリへ変更する場合は `TMPDIR` を上書きしてください。
- **GDAL キャッシュ**: 既定 `GDAL_CACHEMAX=512`。マシンに余裕があれば上げられますが、I/O 飽和時は増やし過ぎないでください。
- **Mapzen (Mapterhorn) との比較**: Mapzen の Mapterhorn タイルはズーム 0–15 が公式レンジ（[ドキュメント](https://raw.githubusercontent.com/tilezen/joerd/master/docs/index.md)）です。本ツールはズーム 16 まで自動出力できるので、地形の細部を 1 段深く表現できます。
- **データサイズ**: Lossless WebP により圧縮しますが、ズーム範囲によっては数十 GB になる場合があります。十分なディスク容量を確保してください。

## コマンド一覧（`just --list` と同等）

```text
just setup                        # pipenv install
just check                        # 依存関係チェック
just bounds <source>              # bounds.csv 生成
just convert <input> <output> [--min-zoom Z] [--max-zoom Z]
just test-sample <source>         # 代表ファイルでの動作確認
just aggregate <source...> [options]
  # -o/--output で PMTiles パスを指定（省略時は output/fusi.pmtiles）
  # 既定で --verbose を有効化し、TMPDIR=output/ と GDAL_CACHEMAX=512 を設定
just inspect <pmtiles>            # PMTiles メタデータ閲覧
just upload                       # output/fusi.pmtiles をリモートへ rsync
just clean / clean-all            # 出力や bounds.csv を削除
```

## タイル仕様

- **タイルサイズ**: 512 × 512 px
- **ズーム範囲**: 既定値は 0–15。ソースの GSD ≈ 1.4 m の場合は自動で 16 が選択されます。
- **Terrarium エンコード**
  - デコード式: `elevation = (R × 256 + G + B / 256) - 32768`
  - nodata は 0 m として出力（RGB ≈ 128/0/0）
  - ズーム別垂直解像度は mapterhorn と同じフォーミュラで 2 のべき乗に丸め
- **メタデータ**: attribution に `国土地理院 (GSI Japan)`、ライセンスとして `R 6JHs 133` を埋め込み
- **PMTiles メタデータ**: `encoding=terrarium`, `tile_type=webp`, attribution は `国土地理院 (GSI Japan)`

### Mapbox Terrain-RGB との比較

| 項目 | fusi (Terrarium) | Mapbox Terrain-RGB |
|------|------------------|--------------------|
| オフセット | +32768 | +10000 |
| 解像度 | 1/256 m (ズーム 19 換算) | 0.1 m |
| nodata | 0 m | -10000 m |
| 用途 | mapterhorn 互換ビジュアライズ | Mapbox/MapLibre 公式タイルセット |

## プロジェクト構成

```text
fusi/
├── source-store/             # ソース GeoTIFF（元ファイル or symlink）
│   └── <source>/
│       ├── *.tif
│       └── bounds.csv        # just bounds で生成
├── output/                   # 変換結果 MBTiles / PMTiles
├── pipelines/
│   ├── source_bounds.py      # bounds.csv 作成
│   ├── convert_terrarium.py  # 単一 GeoTIFF → PMTiles
│   ├── aggregate_pmtiles.py  # 複数 GeoTIFF → MBTiles 集約（+ pmtiles convert）
│   ├── mbtiles_writer.py     # Terrarium WebP タイルを MBTiles に書き出すヘルパ
│   └── inspect_pmtiles.py    # PMTiles のヘッダ確認
├── justfile                  # タスクランナー定義
├── Pipfile / Pipfile.lock    # Python 依存関係
├── IMPLEMENTATION_SUMMARY.md
└── README.md
```

## ロードマップ

- [x] GeoTIFF → Terrarium PMTiles 単体変換
- [x] bounds.csv 生成とメタデータ管理
- [x] nodata を 0 m に正規化する Terrarium 互換処理
- [x] ズーム自動推定 & 512px タイル対応
- [x] 集約パイプラインと進捗表示
- [ ] Downsampling / オーバービュー生成
- [ ] 配布用パッケージング（例: Cloud Storage 連携）

## データのライセンスと出典

測量法に基づく国土地理院長承認（使用）R 6JHs 133

本プロジェクトは国土地理院（GSI）が提供する標高データを加工しています。利用にあたっては測量法の規定に従い、上記の承認番号を含むクレジット表記を行ってください。

## ソフトウェアライセンス

CC0 1.0 Universal（Public Domain Dedication）です。`LICENSE` を参照してください。

## コントリビュート

1. リポジトリを Fork
2. ブランチを作成
3. 変更を実装し `just test-sample` / `just aggregate` などで確認
4. Pull Request を作成

## サポート

- GitHub Issues: [hfu/fusi/issues](https://github.com/hfu/fusi/issues)
- その他連絡先: リポジトリメンテナーまで
