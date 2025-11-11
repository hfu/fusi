# Fusi Pipelines

このディレクトリには、fusi の 2 段階変換パイプラインスクリプトが含まれています。

## スクリプト

### 1. source_bounds.py

GeoTIFF ファイルのメタデータ（バウンディングボックスとラスタサイズ）を抽出し、`bounds.csv` を生成します。

**使用方法:**
```bash
pipenv run python pipelines/source_bounds.py <source_name>
```

**出力:**
- `source-store/<source_name>/bounds.csv`

**CSV 形式:**
```csv
filename,left,bottom,right,top,width,height
sample.tif,15529068.97,4232038.46,15562464.81,4273136.46,1000,1000
```

### 2. convert_terrarium.py

GeoTIFF 標高データを Terrarium エンコーディングで PMTiles に変換します。

**使用方法:**
```bash
pipenv run python pipelines/convert_terrarium.py <input_tif> <output_pmtiles> [--min-zoom MIN] [--max-zoom MAX]
```

**オプション:**
- `--min-zoom`: 最小ズームレベル（デフォルト: 0）
- `--max-zoom`: 最大ズームレベル（デフォルト: 15）

**処理フロー:**
1. GeoTIFF を EPSG:3857 (Web Mercator) に再投影
2. 512×512 ピクセルのタイルに切り出し
3. Terrarium エンコーディング適用（ズームレベル別垂直解像度）
4. Lossless WebP としてエンコード
5. PMTiles 形式でパッケージ化

### 3. aggregate_pmtiles.py

`bounds.csv` を参照して複数の GeoTIFF を統合し、1 つの Terrarium PMTiles を生成します。

**使用方法:**

```bash
pipenv run python pipelines/aggregate_pmtiles.py <source_name> <output_pmtiles> \
  [--min-zoom MIN] [--max-zoom MAX] [--bbox WEST SOUTH EAST NORTH]
```

**主な機能:**

- `bounds.csv` の範囲情報を用いて対象ファイルを自動選別
- 出力タイルごとに必要な GeoTIFF をオンデマンドでモザイク
- 指定した緯度経度範囲のみを切り出して書き出し可能
- `just aggregate` からパイプラインとして実行できる

## Terrarium エンコーディング

### エンコード式

```python
# 標高 (メートル) → RGB
factor = 2 ** (19 - zoom) / 256  # ズームレベル別解像度
elevation_rounded = round(elevation / factor) * factor
offset_elevation = elevation_rounded + 32768

R = floor(offset_elevation / 256)
G = offset_elevation % 256
B = (offset_elevation - floor(offset_elevation)) * 256
```

### デコード式

```python
# RGB → 標高 (メートル)
elevation = (R * 256 + G + B / 256) - 32768
```

### ズームレベル別垂直解像度

mapterhorn 方式に従い、ズームレベルごとに垂直解像度を 2 のべき乗で調整します。

| ズーム | 垂直解像度 | ピクセルサイズ (3857) |
|--------|-----------|---------------------|
| 0      | 2048 m    | 78.3 km            |
| 5      | 64 m      | 2.45 km            |
| 10     | 2 m       | 76.4 m             |
| 12     | 0.5 m     | 19.1 m             |
| 15     | 0.0625 m  | 2.39 m             |
| 19     | 0.0039 m  | 0.149 m            |

この最適化により：

- ファイルサイズを削減
- 各ズームレベルで適切な精度を維持
- 隣接ピクセル間の最小傾斜角度（slope angle）を約 1.5 度に統一（[mapterhorn 仕様](https://github.com/consbio/mapterhorn#vertical-resolution) 参照）

## Mapbox Terrain-RGB との比較

| 項目 | Terrarium (fusi/mapterhorn) | Mapbox Terrain-RGB |
|------|----------------------------|-------------------|
| 基準オフセット | +32768 | +10000 |
| 最小標高 | -32768 m | -10000 m |
| 最大標高 | +32767 m | +6553.5 m |
| 最大解像度 | 1/256 m (3.9 mm) | 0.1 m |
| デコード式 | `(R×256+G+B/256)-32768` | `(R×256²+G×256+B)×0.1-10000` |
| 垂直解像度 | ズーム依存 | 固定 (0.1m) |

Terrarium は以下の利点があります：

- より広い標高範囲（-32768m ～ +32767m）
- ズームレベルに応じた最適化によるファイルサイズ削減
- mapterhorn との互換性

## デコード例

### JavaScript (MapLibre GL JS)

```javascript
// カスタムレイヤーでデコード
map.addLayer({
  id: 'terrain',
  type: 'raster-dem',
  source: 'fusi-terrain',
  encoding: 'terrarium'  // MapLibre は terrarium をサポート
});
```

### Python

```python
import numpy as np
from PIL import Image

# WebP タイルを読み込み
img = Image.open('tile.webp')
rgb = np.array(img)

# デコード
r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
elevation = (r.astype(float) * 256 + g.astype(float) + b.astype(float) / 256) - 32768

print(f"標高範囲: {elevation.min():.1f}m ～ {elevation.max():.1f}m")
```

## 参考文献

- [mapterhorn pipelines](https://github.com/mapterhorn/mapterhorn/tree/main/pipelines) - 本実装の元となった方法論
- [Mapbox Terrain-RGB](https://docs.mapbox.com/data/tilesets/reference/mapbox-terrain-rgb-v1/) - 類似のエンコーディング方式
- [Terrarium Encoding](https://github.com/tilezen/joerd/blob/master/docs/formats.md#terrarium) - Terrarium 形式の説明
