# Fusi site (MapLibre 3D DEM viewer)

使い方（ローカルで PMTiles を提供して 3D 表示を確認する手順）:

1. 事前準備: `pmtiles` CLI がインストールされていること（npm の pmtiles パッケージなど）。

2. PMTiles をサーブする（例: `output/sample_webp.pmtiles` を提供する）:

```bash
# pmtiles CLI を使ってローカルでタイルを配信
pmtiles serve ../output/sample_webp.pmtiles --port 3001
```

3. 別ターミナルでサイトを起動:

```bash
cd site
npm install
npm run dev
```

4. ブラウザで http://localhost:5173 を開くと、地図が表示されます。

注意:
- サイトは `http://localhost:3001/tiles/{z}/{x}/{y}.png` を raster-dem ソースとして使う想定です。`pmtiles serve` が別ポートで提供するタイル URL に合わせて `src/main.js` を編集してください。
- DEM の符号化方式によっては MapLibre の `raster-dem` と互換性がない場合があります（例えば MapLibre が期待する terrainRGB フォーマットではない等）。その場合は PMTiles を提供するサーバ側で適切な PNG (terrainRGB) を出力するか、フロント側で対応する必要があります。
