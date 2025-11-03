# 変換パラメータ（推奨）

このプロジェクトで一括変換を行う前に、`convert.py` のパラメータを調整してください。1m 解像度の地形データに対しての推奨設定を下に示します。

- maxzoom: 17（WebMercator における概算。日本付近では約 1 m/px 相当のズームレベルです）
- tile-format: WEBP（ファイルサイズ対画質のバランスが良いため）
- webp-quality: 80（品質のデフォルト）。デフォルトでは WEBP は lossless にするため、品質指定は通常無効化されます。lossless を無効化する場合は `--webp-lossless` を false にして品質を指定してください。
- addo-resampling: average（DEM をダウンサンプリングする際は平均化が妥当なことが多い）
- approval: 測量法に基づく国土地理院長承認（使用）R 6JHs 133

利用例:

```
pipenv run python convert.py input/your.tif output/your.pmtiles \
  --max-zoom 17 \
  --tile-format WEBP \
  --webp-quality 80 \
  --addo-resampling average \
  --approval "測量法に基づく国土地理院長承認（使用）R 6JHs 133"
```

注意:
- GDAL のビルドによっては `WEBP_QUALITY` の creation option がサポートされないことがあります。その場合、品質指定が無視されるかエラーになります。サーバ上で実行する前に 1~2 件で検証してください。
- PMTiles に書き込まれるメタデータ（description, maxzoom, format, webp_quality）は `convert.py` により MBTiles の metadata テーブルへ挿入されます。
