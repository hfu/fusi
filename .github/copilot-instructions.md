# Copilot / 自動補完向け指示書 — fusi リポジトリ

目的

- このリポジトリは日本の 1m GSD 標高データ（GeoTIFF 約 4,500 ファイル）を PMTiles タイルに変換し、Web 上で 3D 可視化（MapLibre GL JS）を行うためのパイプラインです。

背景とこれまでの作業

- 初期状態は `input/` に大量の GeoTIFF があるのみでした。プロジェクトを素早く動かせるよう、変換スクリプト、タスクランナー（justfile）、およびテストランナーを作成しました。
- 変換パイプラインの主要な流れは: 再投影（EPSG:3857）→ MBTiles（gdal_translate）→ オーバービュー（gdaladdo）→ PMTiles（pmtiles convert）です。
- 単体テストとして入力ディレクトリ内の最大ファイルを自動選択して変換する仕組みを追加しました。
- ユーザー要求により、出力を `docs/` に置き、Vite を使った MapLibre フロントエンドを `docs/` 配下に配置する設計に変更しました（GitHub Pages 配備想定）。
- `convert.py` には、1m 解像度向けの既定 maxzoom（z=17 推奨）、承認番号を含む metadata の挿入、WEBP 品質ヒント、gdaladdo のリサンプリング指定などのオプションを追加済みです。

運用ルール（Copilot がコードを生成・補完する際の指針）

1. 出力先は `docs/` を既定とすること。既存の `output/` は廃止予定で、`just clean` は `output/` を削除して `docs/` を作成する。
2. `convert.py` は CLI ツールとして設計し、出力ファイル名は呼び出し側が指定する形を優先する（ただし上位レシピは `docs/` を指定する）。
3. GDAL の creation options（例: `WEBP_QUALITY`）は環境依存のため、生成コードはそれらが非対応でも失敗しないフォールバックを組み込むこと。
4. 大量処理（4500 ファイル）用のバッチ実装では、次を満たすこと: 並列実行（スレッド/プロセス）、再試行ロジック、成功/失敗のマーカー（例: .done ファイル）、ログ出力の分離（個別ファイルログ）、リソース制限（メモリ/CPU）設定。
5. フロントエンドは `docs/` に配置し、MapLibre GL JS のバージョンは 5.x 系（>=5.0.0）を想定する。`package.json` の依存は `^5.0.0` を指定すること。
6. DEM のエンコーディングに注意すること。MapLibre の `raster-dem` と互換性が無い場合は、terrainRGB など MapLibre が期待する形式に変換するか、サーバ側でレンダリング済み PNG を提供する実装を検討すること。
7. 変更を加える際は、必ず小さな単位でテストを行う（1 ファイルでの確認 → 数十ファイルのバッチ → フルスケール）。
8. 説明文や README 等に含まれる承認番号やクレジットは消さず、出力メタデータにも同じ文字列を入れること。

開発者への注意点（実務的）

- `convert.py` のテストを行う際は、まず GDAL が MBTiles と指定の TILE_FORMAT（WEBP 等）をサポートしているかを確認する小スクリプトを実行すること。
- PMTiles を配信する際は `pmtiles serve` を使うと最も簡単。将来的に CDN 配信や S3 連携をする場合は pmtiles の静的配信用バンドル生成を検討する。
- バッチ並列化はまず GNU Parallel 版を用意し、後から Python multiprocessing 実装に差し替えるのが早くリスクが低い。

ファイルと責務の短い一覧

- `convert.py`: GeoTIFF → PMTiles のメイン変換ロジック（再投影・MBTiles 生成・overviews・metadata 挿入・pmtiles convert）
- `justfile`: 開発タスク（依存インストール、テスト、バッチ変換、サイト起動）
- `scripts/test_sample.py`: largest .tif を選んで convert.py を呼ぶテストランナー
- `docs/`: 静的サイト（Vite + MapLibre）と成果物配置先（PMTiles）

今後の優先タスク（短期）

1. 一括処理の並列バッチスクリプト（エラーハンドリングと再試行付き）を実装
2. WEBP 品質のサポート確認と、未サポート時のフォールバック実装
3. MapLibre 側での DEM 表示確認（terrain 表示・hillshade の品質検証）

---

このファイルは Copilot 系自動補完や他の開発支援エージェントがリポジトリに変更を加える際の作業ルールと背景情報をまとめたものです。変更を行う前にここを参照してください。