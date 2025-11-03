# fusi

日本の標高データ（GeoTIFF 約 4,500 ファイル）を PMTiles の地形タイルに変換するためのツールです。mapterhorn の方法論を踏襲し、Web Mercator（EPSG:3857）で処理します。

## 機能

- 1:1 変換（単一 GeoTIFF → 単一 PMTiles）
- バッチ処理（数千ファイルを並列実行で処理）
- Web Mercator への自動再投影（元座標系からの reprojection）
- mapterhorn 互換のパイプライン思想

## 前提条件

### 必須ツール

1. Python 3.11 以上（pipenv 利用）
1. GDAL ツール一式（gdal2tiles.py を含む）
1. PMTiles CLI（[protomaps/go-pmtiles](https://github.com/protomaps/go-pmtiles)）
1. GNU Parallel（任意：バッチ処理用）

### インストール

#### macOS（Homebrew）

```bash
# GDAL のインストール
brew install gdal

# PMTiles CLI のインストール
curl -LO https://github.com/protomaps/go-pmtiles/releases/latest/download/pmtiles_darwin_arm64.tar.gz
tar -xzf pmtiles_darwin_arm64.tar.gz
sudo mv pmtiles /usr/local/bin/

# GNU Parallel のインストール
brew install parallel
```

#### Ubuntu/Debian

```bash
# GDAL のインストール
sudo apt update
sudo apt install gdal-bin python3-gdal

# PMTiles CLI のインストール
wget https://github.com/protomaps/go-pmtiles/releases/latest/download/pmtiles_linux_x86_64.tar.gz
tar -xzf pmtiles_linux_x86_64.tar.gz
sudo mv pmtiles /usr/local/bin/

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

### 単一ファイルの変換

GeoTIFF 1 ファイルを PMTiles に変換します。

```bash
just convert input/FG-GML-4930-02-28-DEM1A-20250515.tif output/sample.pmtiles
```

### サンプル変換（動作確認）

input ディレクトリの先頭ファイルを使って簡易テストを実行します。

```bash
just test-sample
```

### バッチ処理（全ファイル）

input ディレクトリ内のすべての GeoTIFF を PMTiles に変換します。

```bash
just batch-convert
```

### 利用可能なコマンド一覧

```bash
just --list                    # コマンド一覧の表示
just install                   # 依存関係のインストール
just clean                     # 出力ディレクトリの掃除
just count-files               # 入力ファイル数のカウント
just stats                     # 入出力ディレクトリのサイズ統計
just setup                     # 開発環境セットアップ
just check                     # システム依存関係の確認
```

## プロジェクト構成

```text
fusi/
├── input/                    # GeoTIFF ファイル（~4500 ファイル）
├── output/                   # 生成される PMTiles
├── convert.py                # 変換スクリプト本体
├── Pipfile                   # Python 依存関係
├── justfile                  # タスク自動化
├── README.md                 # 本ファイル
└── .gitignore                # Git 忌避設定
```

## 技術詳細

### 処理パイプライン

1. 入力検証：GeoTIFF の形式・メタデータを確認
1. 再投影：Web Mercator（EPSG:3857）へ変換（bilinear resampling）
1. タイル生成：gdal2tiles.py を用いたラスタタイル生成
1. 形式変換：MBTiles → PMTiles（pmtiles CLI）

### ズームレベル

- 既定レンジ：ズーム 0–15
- 主用途：地形可視化・概観
- バンド構成：標高の単一バンドを想定

### 性能目安

- 単一ファイル：1–3 分程度（サイズ依存）
- バッチ処理：GNU Parallel による並列実行
- 容量：PMTiles により効率的に圧縮・配布

## ロードマップ

- [x] 基本の 1:1 変換（GeoTIFF → PMTiles）
- [ ] Aggregation パイプライン（複数入力 → 単一出力）
- [ ] 概観レベル向けダウンサンプリング
- [ ] 配布向けバンドル生成
- [ ] 品質最適化（垂直解像度の丸め、ブレンド処理）

## 関連プロジェクト

- [mapterhorn](https://github.com/mapterhorn/mapterhorn) — 地形タイルの方法論
- [PMTiles](https://github.com/protomaps/PMTiles) — クラウド最適化タイル形式

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
