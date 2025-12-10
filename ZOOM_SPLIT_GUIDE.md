iine# Zoom分割Aggregate 使用ガイド

## 概要

`fusi`プロジェクトのaggregate処理は、高ズームレベル（z15-16）で大量のタイルを生成する際に、メモリ使用量が40GB以上に達する問題がありました。

この問題を解決するため、**Zoom分割Aggregate**機能を導入しました。ズームレベルを複数のグループに分割して個別に処理し、最後にマージすることで、**メモリ使用量を10GB以下に抑える**ことができます。

## クイックスタート

### 1. 分割パターンの確認

利用可能な分割パターンを確認：

```bash
just show-split-patterns
```

出力例：
```
Split pattern: balanced

Split pattern: 4 groups
------------------------------------------------------------
Group 1: z0-10: ~55,000 tiles, ~6.0GB memory
Group 2: z11-12: ~200,000 tiles, ~8.0GB memory
Group 3: z13-14: ~1,000,000 tiles, ~10.0GB memory
Group 4: z15-16: ~20,000,000 tiles, ~10.0GB memory
------------------------------------------------------------
Total estimated tiles: 21,255,000
Peak memory usage: ~10.0GB
```

### 2. 基本的な使用方法

```bash
# 推奨: balancedパターンで実行（4分割）
just aggregate-split dem1a dem5a dem10b -o output/fusi.pmtiles

# 安全重視: safeパターンで実行（6分割、メモリを確実に抑える）
just aggregate-split dem1a dem5a dem10b \
  -o output/fusi.pmtiles \
  --split-pattern safe

# 速度重視: fastパターンで実行（3分割、高速ストレージ向け）
just aggregate-split dem1a dem5a dem10b \
  -o output/fusi.pmtiles \
  --split-pattern fast
```

### 3. 特定のズーム範囲のみを処理

```bash
# z13-14のみを処理
just aggregate-zoom 13 14 dem1a -o output/fusi-z13-14.mbtiles

# z0-10のみを処理
just aggregate-zoom 0 10 dem1a dem5a dem10b -o output/fusi-z0-10.mbtiles
```

### 4. 複数のMBTilesをマージ

```bash
just merge-mbtiles output/fusi.mbtiles \
  output/fusi-z0-10.mbtiles \
  output/fusi-z11-12.mbtiles \
  output/fusi-z13-14.mbtiles \
  output/fusi-z15-16.mbtiles
```

## 分割パターンの詳細

### balanced（推奨）

**メモリとバランスを両立した4分割パターン**

```
グループ1: z0-10   (~55,000タイル, メモリ: ~6GB)
グループ2: z11-12  (~200,000タイル, メモリ: ~8GB)
グループ3: z13-14  (~1,000,000タイル, メモリ: ~10GB)
グループ4: z15-16  (~20,000,000タイル, メモリ: ~10GB)
```

**推奨環境**: 16GB RAM、標準的なSSD

### safe（安全重視）

**メモリを確実に抑える6分割パターン**

```
グループ1: z0-9    (~14,000タイル, メモリ: ~5GB)
グループ2: z10-11  (~90,000タイル, メモリ: ~6GB)
グループ3: z12     (~130,000タイル, メモリ: ~7GB)
グループ4: z13     (~500,000タイル, メモリ: ~8GB)
グループ5: z14     (~2,000,000タイル, メモリ: ~9GB)
グループ6: z15-16  (~20,000,000タイル, メモリ: ~10GB)
```

**推奨環境**: 16GB RAM以下、安定性を最優先

### fast（速度重視）

**処理時間を短縮する3分割パターン**

```
グループ1: z0-11   (~250,000タイル, メモリ: ~8GB)
グループ2: z12-13  (~1,500,000タイル, メモリ: ~12GB)
グループ3: z14-16  (~22,000,000タイル, メモリ: ~12GB)
```

**推奨環境**: 24GB RAM以上、NVMe SSD

### incremental（デバッグ用）

**各ズームを個別処理する9分割パターン**

```
グループ1: z0-6    (~5,000タイル, メモリ: ~3GB)
グループ2: z7-9    (~9,000タイル, メモリ: ~4GB)
グループ3: z10     (~40,000タイル, メモリ: ~5GB)
グループ4: z11     (~80,000タイル, メモリ: ~6GB)
グループ5: z12     (~130,000タイル, メモリ: ~7GB)
グループ6: z13     (~500,000タイル, メモリ: ~8GB)
グループ7: z14     (~2,000,000タイル, メモリ: ~9GB)
グループ8: z15     (~8,000,000タイル, メモリ: ~10GB)
グループ9: z16     (~12,000,000タイル, メモリ: ~10GB)
```

**推奨環境**: テスト・検証用

## 詳細オプション

### 全オプション一覧

```bash
just aggregate-split [OPTIONS] <sources...>
```

#### 必須引数
- `sources...`: ソース名（例: `dem1a`, `dem5a`, `dem10b`）

#### 主要オプション
- `-o, --output <path>`: 出力PMTilesファイルのパス（既定: `output/fusi.pmtiles`）
- `--split-pattern <pattern>`: 分割パターン（既定: `balanced`）
  - 選択肢: `balanced`, `safe`, `fast`, `incremental`, `single`
- `--resume-from <N>`: グループNから再開（0ベース）
- `--bbox <W S E N>`: WGS84バウンディングボックス（度）
- `--overwrite`: 既存ファイルを上書き
- `--keep-intermediates`: 中間MBTilesファイルを保持

#### パフォーマンスオプション
- `--warp-threads <N>`: warpスレッド数（既定: 1）
- `--io-sleep-ms <N>`: タイルごとのスリープ時間（既定: 1ms）
- `--progress-interval <N>`: 進捗表示の間隔（既定: 200タイル）

#### ログオプション
- `--verbose`: 詳細なログを出力（既定）
- `--silent`: ログを抑制

## 使用例

### 例1: 標準的な使用（16GB RAM）

```bash
# 既定のbalancedパターンで実行
export TMPDIR="$PWD/output"
export GDAL_CACHEMAX=512

just aggregate-split dem1a dem5a dem10b \
  -o output/japan.pmtiles \
  --overwrite
```

### 例2: 安全重視（12-16GB RAM）

```bash
# safeパターンで実行
export TMPDIR="$PWD/output"
export GDAL_CACHEMAX=256

just aggregate-split dem1a dem5a dem10b \
  -o output/japan.pmtiles \
  --split-pattern safe \
  --warp-threads 1 \
  --io-sleep-ms 2 \
  --overwrite
```

### 例3: 速度重視（24GB+ RAM、NVMe SSD）

```bash
# fastパターンで実行
export TMPDIR="$PWD/output"
export GDAL_CACHEMAX=1024

just aggregate-split dem1a dem5a dem10b \
  -o output/japan.pmtiles \
  --split-pattern fast \
  --warp-threads 4 \
  --io-sleep-ms 0 \
  --overwrite
```

### 例4: 特定地域のみ（長崎県）

```bash
just aggregate-split dem1a \
  -o output/nagasaki.pmtiles \
  --bbox 128.3 32.4 131.6 33.8 \
  --split-pattern safe \
  --overwrite
```

### 例5: 中断からの再開

処理が中断した場合、特定のグループから再開できます：

```bash
# グループ2（0ベース、つまり3番目のグループ）から再開
just aggregate-split dem1a dem5a dem10b \
  -o output/japan.pmtiles \
  --resume-from 2 \
  --overwrite
```

### 例6: 中間ファイルを保持（デバッグ用）

```bash
# 中間MBTilesファイルを削除せずに保持
just aggregate-split dem1a \
  -o output/japan.pmtiles \
  --keep-intermediates
```

中間ファイルは以下のような名前で保存されます：
```
output/japan_z0-10.mbtiles
output/japan_z11-12.mbtiles
output/japan_z13-14.mbtiles
output/japan_z15-16.mbtiles
```

## ワークフロー

### 典型的な実行フロー

1. **準備**: bounds.csvを生成
   ```bash
   just bounds dem1a
   just bounds dem5a
   just bounds dem10b
   ```

2. **分割パターンの確認**
   ```bash
   just show-split-patterns
   ```

3. **小規模テスト**（長崎県など）
   ```bash
   just aggregate-split dem1a \
     -o output/test-nagasaki.pmtiles \
     --bbox 128.3 32.4 131.6 33.8 \
     --split-pattern safe \
     --overwrite
   ```

4. **本番実行**
   ```bash
   just aggregate-split dem1a dem5a dem10b \
     -o output/japan.pmtiles \
     --split-pattern balanced \
     --overwrite
   ```

5. **検証**
   ```bash
   just inspect output/japan.pmtiles
   ```

### 処理時間の目安

| パターン | グループ数 | 総処理時間（日本全域） |
|---------|----------|-------------------|
| single  | 1        | 80-100時間（スワップ発生）|
| fast    | 3        | 60-70時間         |
| balanced| 4        | 70-80時間         |
| safe    | 6        | 80-90時間         |
| incremental| 9     | 90-100時間        |

※処理時間はハードウェア構成により大きく変動します

## トラブルシューティング

### Q1: "Out of memory" エラーが発生する

**対策**:
1. より細かい分割パターンを使用: `--split-pattern safe`
2. `GDAL_CACHEMAX`を削減: `export GDAL_CACHEMAX=256`
3. `--warp-threads`を1に設定
4. `--io-sleep-ms`を増やす（例: 2-5ms）

### Q2: 処理が途中で止まる

**対策**:
1. `--verbose`で詳細ログを確認
2. メモリ使用量を監視: `vm_stat 1`（macOS）または `vmstat 1`（Linux）
3. 中断したグループを特定し、`--resume-from`で再開

### Q3: マージ時に重複エラーが発生する

**原因**: 同じタイルが複数のグループに含まれている

**対策**:
1. 中間ファイルを削除して最初からやり直す
2. 分割パターンが正しいか確認: `just show-split-patterns`
3. 手動でマージする場合は、重複検証をスキップ: `--no-verify`（非推奨）

### Q4: PMTiles変換が失敗する

**原因**: `pmtiles`コマンドが見つからない、またはMBTilesに問題がある

**対策**:
1. `pmtiles`コマンドをインストール: `brew install golang && go install github.com/protomaps/go-pmtiles/cmd/pmtiles@latest`
2. MBTilesを直接確認: `sqlite3 output/fusi.mbtiles "SELECT COUNT(*) FROM tiles;"`
3. Pythonフォールバックが使用される場合がある（遅いが動作する）

### Q5: 中間ファイルが大量に残る

**原因**: `--keep-intermediates`が指定されている、またはエラーで処理が中断した

**対策**:
```bash
# 中間ファイルを手動で削除
rm output/fusi_z*.mbtiles
```

## パフォーマンスチューニング

### 16GB RAM + USB 3.0 SSD（推奨設定）

```bash
export TMPDIR="$PWD/output"
export GDAL_CACHEMAX=512

just aggregate-split dem1a dem5a dem10b \
  -o output/japan.pmtiles \
  --split-pattern balanced \
  --warp-threads 2 \
  --io-sleep-ms 1 \
  --progress-interval 1000 \
  --overwrite
```

### 32GB RAM + NVMe SSD（高速設定）

```bash
export TMPDIR="$PWD/output"
export GDAL_CACHEMAX=2048

just aggregate-split dem1a dem5a dem10b \
  -o output/japan.pmtiles \
  --split-pattern fast \
  --warp-threads 8 \
  --io-sleep-ms 0 \
  --progress-interval 5000 \
  --overwrite
```

### 8-12GB RAM（安全設定）

```bash
export TMPDIR="$PWD/output"
export GDAL_CACHEMAX=256

just aggregate-split dem1a dem5a dem10b \
  -o output/japan.pmtiles \
  --split-pattern incremental \
  --warp-threads 1 \
  --io-sleep-ms 2 \
  --progress-interval 500 \
  --overwrite
```

## モニタリング

### メモリ使用量の監視

**macOS**:
```bash
# 別ターミナルで実行
vm_stat 1
```

**Linux**:
```bash
# 別ターミナルで実行
vmstat 1
```

### USS（Unique Set Size）モニタリング（新機能）

`split_aggregate`はグループごとの処理中に、プロセスが実際に占有しているメモリ量の
より正確な指標である「USS（Unique Set Size）」のピークを計測してログに出力します。

ポイント:
- **何が計測されるか**: 可能な場合は `psutil` の `memory_full_info().uss` を利用します。利用できない環境では、プロセス本体と子プロセスのRSSを合計した「最良推定値」を出力します。
- **出力例**: グループ処理時の標準ログに以下のような行が追加されます。

```
Memory before group 3: 1.9GB
Memory after group 3: 2.3GB
Memory delta for group 3: 400MB
USS peak during group 3: 9.6GB
```

- **解釈**:
  - `RSS`（Resident Set Size）はプロセスが物理メモリ上に割り当てられている総量を示しますが、共有ライブラリやカーネルキャッシュなどが含まれるため、実際にプロセス固有で消費しているメモリは過大評価されることがあります。
  - `USS`はそのうち「そのプロセスだけが占有する」領域を示すため、実稼働でのメモリ需要の評価により適しています。USSがターゲット（例: 10GB）に近い/超える場合は、ズーム分割を細かくするか、設定（`GDAL_CACHEMAX`や`--warp-threads`）を見直してください。
  - もしUSSが得られない環境（`psutil`未導入など）では、出力されるRSSベースの値は上限的な目安として扱ってください。

- **運用上の推奨行動**:
  1. 新しい大きな処理を実行するときは、まず小さなグループ（例: `--split-pattern safe`）でプロファイルを取り、`USS peak` を確認してください。
 2. USSが十分低ければ `balanced` に移行して再実行します。
 3. USSが目標に近い・超える場合は、さらに細かい分割を作るか（カスタム分割）、`--io-sleep-ms` を増やすか、`--warp-threads` を減らすなどでメモリ負荷を下げてください。

注: この記事時点でUSS計測は `split_aggregate` にデフォルトで組み込まれており、無効化するCLIフラグはありません。無効化やサンプリング間隔のカスタマイズを希望する場合は知らせてください。実装を追加します。


### ディスクI/Oの監視

**macOS**:
```bash
iostat -w 1
```

**Linux**:
```bash
iostat -x 1
```

### プロセスのリソース使用量

```bash
# Pythonプロセスを監視
top -pid $(pgrep -f aggregate)
```

## 既存のaggregateタスクとの比較

| 機能 | `just aggregate` | `just aggregate-split` |
|-----|-----------------|----------------------|
| メモリ使用量 | 40GB+ | 10GB以下 |
| 処理時間 | 基準 | +10-20% |
| 中断時の復旧 | 困難 | 容易 |
| ディスク使用量 | 基準 | 2倍（中間ファイル） |
| 安定性 | スワップ発生 | 安定 |
| 推奨環境 | 32GB+ RAM | 16GB RAM |

## 次のステップ

1. **小規模テスト**: まず小さな地域（長崎県など）でテストする
2. **パターン選択**: ハードウェア環境に応じた分割パターンを選択
3. **モニタリング**: 初回実行時はメモリとI/Oを監視する
4. **最適化**: 環境に応じてオプションをチューニング
5. **本番実行**: 全国データで実行

## 参考資料

- [MEMORY_OPTIMIZATION_STRATEGY.md](./MEMORY_OPTIMIZATION_STRATEGY.md) - 詳細な戦略と設計
- [PARAMETERS.md](./PARAMETERS.md) - パラメータ分析ガイド
- [README.md](./README.md) - プロジェクト全体のドキュメント
