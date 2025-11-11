# fusi

日本の標高データ（GeoTIFF 約 4,500 ファイル）を PMTiles の地形タイルに変換するためのツールです。mapterhorn の方法論を踏襲し、Terrarium エンコーディングを使用して Web Mercator（EPSG:3857）で処理します。

## 機能

- GeoTIFF メタデータ管理（bounds.csv 生成）
- 2段階変換パイプライン（メタデータ生成 → タイル変換）
- Web Mercator への自動再投影（元座標系からの reprojection）
- Terrarium エンコーディング（mapterhorn 互換）
- ズームレベル毎の垂直解像度最適化
- Lossless WebP タイル生成
- バッチ処理（数千ファイルを並列実行で処理）

## 前提条件

### 必須ツール

1. Python 3.11 以上（pipenv 利用）
1. GNU Parallel（任意：バッチ処理用）

### インストール

#### macOS（Homebrew）

```bash
# GNU Parallel のインストール
brew install parallel
```

#### Ubuntu/Debian

```bash
# GNU Parallel のインストール
sudo apt install parallel
```

## セットアップ

1. リポジトリの取得と移動

```bash
git clone https://github.com/hfu/fusi.git
cd fusi
```

1. Python 依存関係のインストール

```bash
just setup
```

1. システム依存関係の確認

```bash
just check
```

## 使い方

### ソースデータの準備

GeoTIFF ファイルを `source-store/<source_name>/` ディレクトリに配置します。

```bash
mkdir -p source-store/japan_dem
# GeoTIFFファイルをコピー
cp /path/to/geotiffs/*.tif source-store/japan_dem/
```

### ステップ1: Bounds.csv 生成

各 GeoTIFF のバウンディングボックスとメタデータを抽出します。

```bash
just bounds japan_dem
```

これにより `source-store/japan_dem/bounds.csv` が生成されます。

### ステップ2: 単一ファイルの変換

GeoTIFF 1 ファイルを PMTiles に変換します。

```bash
just convert source-store/japan_dem/sample.tif output/sample.pmtiles
```

ズームレベルを指定する場合：

```bash
just convert source-store/japan_dem/sample.tif output/sample.pmtiles 0 15
```

### サンプル変換（動作確認）

source-store 内の先頭ファイルを使って簡易テストを実行します。

```bash
just test-sample japan_dem
```

### バッチ処理（全ファイル）

source-store 内のすべての GeoTIFF を PMTiles に変換します。

```bash
just batch-convert japan_dem
```

### 利用可能なコマンド一覧

```bash
just --list                              # コマンド一覧の表示
just install                             # 依存関係のインストール
just setup                               # 開発環境セットアップ
just bounds <source_name>                # bounds.csv 生成
just convert <input> <output> [min] [max] # 単一ファイル変換
just test-sample <source_name>           # サンプル変換（動作確認）
just batch-convert <source_name>         # バッチ処理（全ファイル）
just clean                               # 出力ディレクトリの掃除
just clean-all                           # 出力と bounds.csv の削除
just check                               # システム依存関係の確認
just config                              # 現在の設定を表示
just inspect <pmtiles_file>              # PMTiles ファイルのメタデータを表示
```

## プロジェクト構成

```text
fusi/
├── source-store/             # ソースデータ管理
│   └── <source_name>/       # ソース毎のディレクトリ
│       ├── *.tif            # GeoTIFF ファイル（~4500 ファイル）
│       └── bounds.csv       # バウンディングボックスメタデータ
├── output/                  # 生成される PMTiles
├── pipelines/               # 変換パイプライン
│   ├── source_bounds.py    # bounds.csv 生成スクリプト
│   └── convert_terrarium.py # Terrarium 変換スクリプト
├── Pipfile                  # Python 依存関係
├── justfile                 # タスク自動化
└── README.md                # 本ファイル
```

## 技術詳細

### 処理パイプライン

**2段階方式：メタデータ管理 + タイル変換**

#### ステージ1: メタデータ生成 (bounds.csv)

- 全 GeoTIFF について EPSG:3857 でのバウンディングボックスを抽出
- ピクセルサイズと解像度を記録
- CSV 形式で管理（mapterhorn 互換）

#### ステージ2: タイル変換

1. **Reprojection**: GeoTIFF を Web Mercator (EPSG:3857) へ再投影
2. **Tiling**: 512×512 ピクセル単位でタイル切り出し
3. **Terrarium Encoding**: 標高値を RGB にエンコード
4. **WebP Encoding**: Lossless WebP として保存
5. **PMTiles Packaging**: PMTiles 形式にアーカイブ

### Terrarium エンコーディング

mapterhorn 互換の Terrarium 形式を採用：

- **基本式**: `elevation = (R × 256 + G + B / 256) - 32768`
- **オフセット**: -32768m（海溝対応）
- **最大解像度**: 1/256 m ≈ 3.9 mm（ズーム19）
- **垂直解像度の最適化**: ズームレベル毎に 2 のべき乗で丸め

#### ズームレベル別垂直解像度

| ズーム | ピクセルサイズ (3857) | 垂直解像度 |
|--------|---------------------|----------|
| 0      | 78.3 km            | 2048 m   |
| 5      | 2.45 km            | 64 m     |
| 10     | 76.4 m             | 2 m      |
| 11     | 38.2 m             | 1 m      |
| 12     | 19.1 m             | 50 cm    |
| 15     | 2.39 m             | 6.3 cm   |
| 19     | 0.149 m            | 3.9 mm   |

この最適化により、全ズームレベルで隣接ピクセル間の最小傾斜角（標高差から計算される最小の斜面角度）を一定（約1.5度）に保ちます。  
（*この「最小角度」は、隣接ピクセル間で表現可能な最小の傾斜角を指し、地形の細部表現の一貫性を保つための設計です。詳しくは [mapterhorn の解説](https://github.com/consbio/mapterhorn#vertical-resolution) も参照してください。*）

### Mapbox Terrain-RGB との違い

| 項目 | Terrarium (fusi) | Mapbox Terrain-RGB |
|------|------------------|-------------------|
| オフセット | +32768 | +10000 |
| 基準値 | -32768m | -10000m |
| 最大解像度 | 1/256 m (3.9 mm) | 0.1 m |
| デコード式 | `(R×256+G+B/256)-32768` | `(R×256²+G×256+B)×0.1-10000` |
| 互換性 | mapterhorn | Mapbox/MapLibre |

### ズームレベル

- 既定レンジ：ズーム 0–15
- カスタマイズ可能：`just convert` コマンドで指定
- 主用途：地形可視化・概観

### 性能目安

- 単一ファイル：1–3 分程度（サイズ依存）
- バッチ処理：GNU Parallel による並列実行
- 容量：Lossless WebP により効率的に圧縮

## ロードマップ

- [x] 基本の 1:1 変換（GeoTIFF → PMTiles）
- [x] GeoTIFF ファイルの矩形（bounds）算出機能（mapterhorn 方式）
- [x] Terrarium エンコーディング（mapterhorn 互換）
- [x] ズームレベル別垂直解像度最適化
- [ ] Aggregation パイプライン（複数入力 → 単一出力、ブレンド処理）
- [ ] Downsampling パイプライン（オーバービュー生成）
- [ ] 配布向けバンドル生成

## 関連プロジェクト

- [mapterhorn](https://github.com/mapterhorn/mapterhorn) — 地形タイルの方法論（本実装の参考）
- [PMTiles](https://github.com/protomaps/PMTiles) — クラウド最適化タイル形式
- [pmtiles-python](https://github.com/protomaps/PMTiles/tree/main/python) — PMTiles Python ライブラリ
- [Mapbox Terrain-RGB](https://docs.mapbox.com/data/tilesets/reference/mapbox-terrain-rgb-v1/) — 別のエンコーディング方式

## データのライセンスと出典

測量法に基づく国土地理院長承認（使用）R 6JHs 133

本プロジェクトは国土地理院（GSI）が提供する標高データを加工・配布します。利用は日本の測量法に従い、上記の承認表示に基づく適切なクレジット表記が必要です。

## ライセンス

CC0 1.0 Universal（CC0 1.0）Public Domain Dedication — 詳細は `LICENSE` を参照してください。

## コントリビュート

1. リポジトリを Fork する
1. フィーチャーブランチを作成する
1. 変更を加える
1. サンプルデータで動作確認する
1. Pull Request を送る

## サポート

ご質問や不具合報告は以下までお願いします。

- GitHub Issues: [hfu/fusi/issues](https://github.com/hfu/fusi/issues)
- Email: Contact repository maintainer
