import 'maplibre-gl/dist/maplibre-gl.css';
import maplibregl from 'maplibre-gl';

// Configuration: point to the pmtiles server that serves your PMTiles as XYZ tiles.
// Example: run `pmtiles serve ../output/your.pmtiles --port 3001` and use the tile template below.
const PMTILES_TILE_URL = 'http://localhost:3001/tiles/{z}/{x}/{y}.png';

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {
      // Simple raster basemap from OpenStreetMap as background
      osm: {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256
      }
    },
    layers: [
      {
        id: 'osm-layer',
        type: 'raster',
        source: 'osm'
      }
    ]
  },
  center: [139.692, 35.6895], // 東京付近を中心に
  zoom: 13
});

map.on('load', () => {
  // Add the raster-dem source backed by the PMTiles server (served as XYZ PNG tiles)
  map.addSource('terrain-dem', {
    type: 'raster-dem',
    tiles: [PMTILES_TILE_URL],
    tileSize: 256,
    // Adjust maxzoom to match your PMTiles metadata (1m data -> z ~ 17)
    maxzoom: 17
  });

  // Use the dem as map terrain (3D)
  map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 });

  // Add a hillshade layer on top of the terrain
  map.addLayer({
    id: 'hillshade',
    type: 'hillshade',
    source: 'terrain-dem'
  });

  // Add a small UI control
  map.addControl(new maplibregl.NavigationControl(), 'top-left');
});
