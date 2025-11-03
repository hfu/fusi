import 'maplibre-gl/dist/maplibre-gl.css';
import maplibregl from 'maplibre-gl';
import { registerMaplibreProtocol } from 'pmtiles-maplibre';

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {
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
  center: [139.692, 35.6895],
  zoom: 13
});

const PMTILES_LOCAL_PATH = '/sample_webp.pmtiles';

// Register pmtiles protocol and add terrain source
try {
  registerMaplibreProtocol(map);
  const pmtilesUrl = `pmtiles://${PMTILES_LOCAL_PATH}`;
  map.addSource('terrain-dem', {
    type: 'raster-dem',
    tiles: [pmtilesUrl + '/{z}/{x}/{y}.png'],
    tileSize: 256,
    maxzoom: 17
  });

  map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 });
  map.addLayer({ id: 'hillshade', type: 'hillshade', source: 'terrain-dem' });
  map.addControl(new maplibregl.NavigationControl(), 'top-left');
  console.log('PMTiles protocol registered; using bundled pmtiles client.');
} catch (err) {
  console.warn('pmtiles registration failed, falling back to XYZ server (if available):', err);
  const PMTILES_XYZ = 'http://localhost:3001/tiles/{z}/{x}/{y}.png';
  map.addSource('terrain-dem', {
    type: 'raster-dem',
    tiles: [PMTILES_XYZ],
    tileSize: 256,
    maxzoom: 17
  });

  map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 });
  map.addLayer({ id: 'hillshade', type: 'hillshade', source: 'terrain-dem' });
  map.addControl(new maplibregl.NavigationControl(), 'top-left');
}
