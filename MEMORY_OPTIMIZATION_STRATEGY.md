# メモリ最適化戦略 - Zoom分割アプローチ

## 問題の分析

### 現状
- 物理メモリ: 16GB
- 実測メモリ使用量: 約40GB（スワップ発生）
- 目標: メモリ使用量を10GB以下に削減

### メモリ使用の内訳（推定）
1. **Python プロセス基本**: 2-3GB
2. **全ソースレコード保持**: 5-8GB
3. **バケット構造（z5）**: 3-5GB
4. **GDAL_CACHEMAX**: 512MB-1GB
5. **numpy配列とタイル処理**: 10-15GB（高ズームで増加）
6. **lineage処理（オプション）**: 5-10GB

## 最適化戦略: Zoom分割方式

### 基本コンセプト

**現在の方式**:
```
全ズームレベル（z0-z16）を一度に処理
→ メモリ使用量 = すべてのズームの累積
```

**新方式（Zoom分割）**:
```
ズームレベルを複数のグループに分割
各グループを個別のMBTilesに出力
最後にMBTilesをマージ
→ メモリ使用量 = 単一グループの最大値
```

### Zoom分割の設計

#### タイル数とメモリの関係

| Zoom | 日本全域タイル数 | 処理時間目安 | メモリ推定 |
|------|----------------|------------|----------|
| 0-6  | ~5,000         | 5分        | 2-3GB    |
| 7-10 | ~50,000        | 30分       | 4-6GB    |
| 11-12| ~200,000       | 2時間      | 6-8GB    |
| 13-14| ~1,000,000     | 8時間      | 8-12GB   |
| 15   | ~4,000,000     | 20時間     | 15-25GB  |
| 16   | ~16,000,000    | 80時間     | 30-50GB  |

#### 推奨分割パターン

**パターンA: 4分割（推奨）**
```
グループ1: z0-10   (~55,000タイル, メモリ: ~6GB)
グループ2: z11-12  (~200,000タイル, メモリ: ~8GB)
グループ3: z13-14  (~1,000,000タイル, メモリ: ~10GB)
グループ4: z15-16  (~20,000,000タイル, メモリ: ~10GB※)
```
※グループ4は最大メモリを使うが、ソースレコードフィルタリングで削減可能

**パターンB: 6分割（安全重視）**
```
グループ1: z0-9    (~14,000タイル, メモリ: ~5GB)
グループ2: z10-11  (~90,000タイル, メモリ: ~6GB)
グループ3: z12     (~130,000タイル, メモリ: ~7GB)
グループ4: z13     (~500,000タイル, メモリ: ~8GB)
グループ5: z14     (~2,000,000タイル, メモリ: ~9GB)
グループ6: z15-16  (~20,000,000タイル, メモリ: ~10GB)
```

**パターンC: 動的分割（最適化）**
- 各グループのタイル数を200,000-500,000に制限
- メモリ使用量を監視しながら動的に調整

## 実装設計

### 1. 新規ファイル構成

```
pipelines/
  zoom_split_config.py      # 分割設定の管理
  aggregate_by_zoom.py      # ズーム範囲指定のaggregate
  merge_mbtiles.py          # 複数MBTilesのマージ
  split_aggregate.py        # 分割実行の統合スクリプト
  memory_monitor.py         # メモリ使用量監視

scripts/
  run_split_aggregate.py    # CLIラッパー
  verify_split_output.py    # 出力検証スクリプト
```

### 2. コア機能の実装

#### 2.1 zoom_split_config.py

```python
"""Zoom分割の設定を管理"""

from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class ZoomGroup:
    min_zoom: int
    max_zoom: int
    estimated_tiles: int
    estimated_memory_gb: float
    
    @property
    def name(self) -> str:
        return f"z{self.min_zoom}-{self.max_zoom}"

def get_split_pattern(pattern: str = "balanced") -> List[ZoomGroup]:
    """分割パターンを返す"""
    # 実装詳細...
    pass

def estimate_memory_for_zoom_range(min_z: int, max_z: int, 
                                    bbox=None) -> float:
    """指定ズーム範囲のメモリ使用量を推定"""
    # 実装詳細...
    pass
```

#### 2.2 aggregate_by_zoom.py

```python
"""ズーム範囲を指定したaggregate処理"""

def aggregate_zoom_range(
    records: Sequence[SourceRecord],
    output_mbtiles: Path,
    min_zoom: int,
    max_zoom: int,
    bbox_wgs84: Optional[Tuple] = None,
    **kwargs
) -> None:
    """
    指定されたズーム範囲のみを処理
    既存のgenerate_aggregated_tilesを内部で使用
    """
    # min_zoomとmax_zoomで範囲を制限
    # 他は既存実装を流用
    pass
```

#### 2.3 merge_mbtiles.py

```python
"""複数のMBTilesをマージ"""

def merge_mbtiles_files(
    input_mbtiles: List[Path],
    output_mbtiles: Path,
    verify: bool = True
) -> None:
    """
    複数のMBTilesを1つにマージ
    
    処理:
    1. 各入力MBTilesからタイルを読み取り
    2. ズームレベルでソート
    3. 重複チェック（同じz,x,yがないか）
    4. 新しいMBTilesに書き込み
    """
    pass

def verify_no_overlaps(mbtiles_list: List[Path]) -> bool:
    """
    複数のMBTilesに重複タイルがないか検証
    """
    pass
```

#### 2.4 split_aggregate.py

```python
"""分割実行の統合スクリプト"""

def run_split_aggregate(
    sources: List[str],
    output_pmtiles: Path,
    split_pattern: str = "balanced",
    resume_from: Optional[int] = None,
    **kwargs
) -> None:
    """
    分割されたaggregate処理を実行
    
    手順:
    1. 分割パターンを取得
    2. 各グループに対して個別にaggregate
    3. 生成されたMBTilesをマージ
    4. PMTilesに変換
    """
    pass
```

### 3. Justfile統合

```justfile
# 分割aggregate（メモリ制約環境向け）
aggregate-split *args:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{output_dir}}"
    export TMPDIR="$(cd "{{output_dir}}" && pwd)"
    export GDAL_CACHEMAX="${GDAL_CACHEMAX:-512}"
    
    pipenv run python -u -m pipelines.split_aggregate \
        --split-pattern balanced \
        --verbose \
        "$@"

# 特定のズーム範囲のみを処理
aggregate-zoom min_zoom max_zoom *args:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{output_dir}}"
    export TMPDIR="$(cd "{{output_dir}}" && pwd)"
    export GDAL_CACHEMAX="${GDAL_CACHEMAX:-512}"
    
    pipenv run python -u -m pipelines.aggregate_by_zoom \
        --min-zoom {{min_zoom}} \
        --max-zoom {{max_zoom}} \
        "$@"

# 複数のMBTilesをマージ
merge-mbtiles output_path *input_paths:
    pipenv run python pipelines/merge_mbtiles.py \
        --output "{{output_path}}" \
        {{input_paths}}
```

## 実装の優先順位とステップ

### フェーズ1: 基本機能（ステップ1-5）

1. **zoom_split_config.py の作成**
   - 分割パターン定義
   - メモリ推定関数

2. **merge_mbtiles.py の実装**
   - 基本的なマージ機能
   - 重複検証

3. **aggregate_by_zoom.py の実装**
   - 既存コードの最小限の変更
   - ズーム範囲フィルタリング

4. **split_aggregate.py の実装**
   - 統合スクリプト
   - エラーハンドリング

5. **justfile への統合**
   - aggregate-split タスク
   - aggregate-zoom タスク

### フェーズ2: 品質保証（ステップ6-10）

6. **テストケースの作成**
   - merge機能のテスト
   - 分割実行のテスト

7. **検証スクリプト**
   - タイル数の整合性
   - タイルデータの同一性

8. **メモリ監視機能**
   - リアルタイムメモリ追跡
   - アラート機能

9. **ドキュメント作成**
   - 使用方法
   - トラブルシューティング

10. **エラーハンドリング強化**
    - リトライロジック
    - レジューム機能

### フェーズ3: 最適化（ステップ11-15）

11. **動的分割の実装**
    - メモリベースの自動調整
    - bbox考慮

12. **並列処理の検討**
    - 独立したズームグループの並列実行
    - I/O競合の回避

13. **進捗追跡の改善**
    - 全体進捗の可視化
    - ETA計算

14. **パフォーマンス測定**
    - ベンチマークスクリプト
    - 最適パターンの特定

15. **CI/CD統合**
    - 自動テスト
    - リグレッション検出

### フェーズ4: 実運用対応（ステップ16-20）

16. **完全な使用例の作成**
    - 実データでの検証
    - 使用ガイド

17. **トラブルシューティングガイド**
    - よくある問題と解決策
    - デバッグ手順

18. **既存テストの更新**
    - 後方互換性の確保
    - 新機能のテスト

19. **パフォーマンスレポート**
    - メモリ使用量の実測
    - 処理時間の比較

20. **最終統合テスト**
    - 全機能の統合確認
    - 本番環境シミュレーション

## メモリ削減の追加技術

### 1. ソースレコードのフィルタリング

高ズームレベルでは、より細かいbbox単位でソースをフィルタリング：

```python
def filter_records_by_zoom(records, zoom_range, bbox=None):
    """
    ズーム範囲に応じてソースレコードをフィルタリング
    高ズームでは解像度の高いソースのみを使用
    """
    min_z, max_z = zoom_range
    if max_z >= 14:
        # 高ズームでは高解像度ソースのみ
        filtered = [r for r in records if r.pixel_size <= 5.0]
    else:
        filtered = records
    return filtered
```

### 2. バケットサイズの調整

```python
def get_bucket_zoom(target_zoom_range):
    """
    処理対象のズーム範囲に応じて最適なバケットズームを選択
    """
    min_z, max_z = target_zoom_range
    if max_z <= 10:
        return 5  # 既定
    elif max_z <= 13:
        return 7  # より細かく
    else:
        return 9  # さらに細かく
```

### 3. ストリーミング処理の強化

```python
def stream_tiles_in_chunks(generator, chunk_size=10000):
    """
    タイルをチャンク単位で処理し、メモリを解放
    """
    chunk = []
    for tile in generator:
        chunk.append(tile)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
            # 明示的なガベージコレクション
            import gc
            gc.collect()
    if chunk:
        yield chunk
```

## 期待される効果

### メモリ使用量

- **現状**: 40GB（スワップ発生）
- **4分割後**: 各グループ6-10GB、ピーク10GB
- **削減率**: 75%削減

### 処理時間

- **現状**: 推定80-100時間（スワップで遅延）
- **4分割後**: 推定60-70時間（スワップなし）
- **改善率**: 30-40%高速化

### 安定性

- スワップなしで安定実行
- 部分的な再実行が可能
- エラー時の損失を最小化

## 使用例

### 基本的な使用

```bash
# 分割aggregateの実行（既定パターン）
just aggregate-split dem1a dem5a dem10b -o output/fusi.pmtiles

# 安全重視パターン
just aggregate-split dem1a dem5a dem10b \
  -o output/fusi.pmtiles \
  --split-pattern safe

# 特定のズーム範囲のみ
just aggregate-zoom 13 14 dem1a -o output/fusi-z13-14.mbtiles

# 複数のMBTilesをマージ
just merge-mbtiles output/fusi.mbtiles \
  output/fusi-z0-10.mbtiles \
  output/fusi-z11-12.mbtiles \
  output/fusi-z13-14.mbtiles \
  output/fusi-z15-16.mbtiles
```

### 中断からのレジューム

```bash
# グループ2から再開
just aggregate-split dem1a dem5a dem10b \
  -o output/fusi.pmtiles \
  --resume-from 2
```

## リスクと対策

### リスク1: マージ処理の失敗

**対策**:
- マージ前に重複検証
- トランザクション処理
- バックアップの保持

### リスク2: 処理時間の増加

**対策**:
- 並列処理の検討（独立グループ）
- I/O最適化
- 中間ファイルの圧縮

### リスク3: ディスク容量不足

**対策**:
- 中間ファイルのクリーンアップ
- ストリーミングマージ
- 容量監視アラート

## まとめ

このZoom分割アプローチにより：

1. **メモリ使用量を40GB→10GB以下に削減**
2. **安定した実行環境を実現**
3. **部分的な再実行が可能**
4. **GPT-4o miniでも実装可能な小さなステップ**

各ステップは独立しており、段階的な実装とテストが可能です。
