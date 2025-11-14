# fusi

`fusi` は国土地理院の約 4,700 枚の標高 GeoTIFF を Terrarium 形式の PMTiles に変換するツールチェーンです。mapterhorn が示した手法をベースに、Web Mercator（EPSG:3857）への自動再投影やズーム別の垂直解像度管理を備えています。2025 年現在、フルデータセット（4,694 ファイル）をズーム 0–16 で 1 本の PMTiles にまとめることを確認済みです。

## 主な特徴

- `bounds.csv` による GeoTIFF メタデータ管理と空間インデックス
- 512px タイルを前提にした自動ズーム推定（GSD から max zoom を決定）
- Terrarium エンコード（mapterhorn 互換）と nodata を 0 m に正規化する安全策
- Lossless WebP タイルを PMTiles にストリーミング書き込み
- 集約パイプライン：複数 GeoTIFF をオンザフライでモザイクし 1 本の PMTiles に統合
- 進捗表示：候補タイル数・書き出しタイル数・割合を標準出力に逐次表示
- `just` コマンドで一連のタスクを自動化

## 必要なもの

- Python 3.12 以上
- pipenv
- just（Homebrew: `brew install just`）
- （任意）GNU Parallel ― `just batch-convert` 実行時に使用

### 参考: ツールの導入例

```bash
brew install just parallel   # macOS
pip3 install --user pipenv
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

### 2. 単一 GeoTIFF の変換

```bash
just convert source-store/bulk_all/sample.tif output/sample.pmtiles
```

- `--max-zoom` を省略すると、ソースの Ground Sample Distance (GSD) からズームを自動推定します。
- 実行ログに「Auto-selected max zoom …」が表示されます。

### 3. 複数 GeoTIFF の集約

```bash
just aggregate bulk_all output/bulk_all.pmtiles
```

- `bounds.csv` から対象ファイルを抽出し、各タイルごとに再投影・モザイク・Terrarium エンコードを行います。
- 標準出力にはズーム別の候補タイル数と進捗率が表示されます。
	- 例: フルデータセット（4,694 枚）では 1,996,833 候補をスキャンし、24,540 枚のタイルを書き出しました。
- オプション
	- `--bbox <west> <south> <east> <north>`: WGS84 度で出力範囲を限定
	- `--min-zoom`, `--max-zoom`: 出力ズームレンジを明示指定
	- `--progress-interval 1000`: 進捗ログの間隔を調整

### 4. 出力の確認

```bash
just inspect output/bulk_all.pmtiles
```

ヘッダ情報・ズームレンジ・バウンディングボックスなどが確認できます。

### 5. 配布先へのアップロード（任意）

```bash
just upload
```

`output/fusi.pmtiles` を想定したアップロードタスクです。宛先やファイル名を変える場合は `justfile` の `upload` レシピを調整してください。

## 実務で得た Tips

- **テストから本番へ**: 小さなサブセットで `just aggregate` を試し、ズーム自動推定や nodata=0 m の挙動を確認してから全量処理すると安全です。
- **進捗ログ**: 大量データのときは出力が数時間続くことがあります。進捗ログには「書き出し済みタイル数」「チェック済み候補数」「全候補に対する割合」が表示されるため、残り時間の目安になります。
- **Mapzen (Mapterhorn) との比較**: Mapzen の Mapterhorn タイルはズーム 0–15 が公式レンジ（[ドキュメント](https://raw.githubusercontent.com/tilezen/joerd/master/docs/index.md)）です。本ツールはズーム 16 まで自動出力できるので、地形の細部を 1 段深く表現できます。
- **データサイズ**: Lossless WebP により圧縮しますが、ズーム範囲によっては数十 GB になる場合があります。十分なディスク容量を確保してください。

## コマンド一覧（`just --list` と同等）

```text
just setup                        # pipenv install
just check                        # 依存関係チェック
just bounds <source>              # bounds.csv 生成
just convert <input> <output> [--min-zoom Z] [--max-zoom Z]
just test-sample <source>         # 代表ファイルでの動作確認
just batch-convert <source>       # GNU Parallel を使った一括変換
just aggregate <source> <output> [options]
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
├── output/                   # 変換結果 PMTiles
├── pipelines/
│   ├── source_bounds.py      # bounds.csv 作成
│   ├── convert_terrarium.py  # 単一 GeoTIFF → PMTiles
│   ├── aggregate_pmtiles.py  # 複数 GeoTIFF → PMTiles 集約
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
