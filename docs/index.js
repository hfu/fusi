// Simple docs/index.js — uses MapLibre CDN and an XYZ PMTiles server for raster-dem
const PMTILES_XYZ = 'http://localhost:3001/tiles/{z}/{x}/{y}.png';

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
      { id: 'osm-layer', type: 'raster', source: 'osm' }
    ]
  },
  center: [139.692, 35.6895],
  zoom: 13
});

map.on('load', async () => {
  // Try to register a pmtiles:// protocol handler using the pmtiles UMD (loaded from CDN in index.html).
  // If registration fails, fall back to a local pmtiles server serving XYZ tiles.
  try {
    if (typeof PMTiles === 'undefined') throw new Error('PMTiles UMD not found');

    // Open the PMTiles archive (same-origin path in docs/)
    const pm = new PMTiles('/sample_webp.pmtiles');
    if (typeof pm.open === 'function') await pm.open();

    // Save original fetch
    const _origFetch = window.fetch.bind(window);

    // Intercept fetch requests for pmtiles:// scheme and serve bytes from the PMTiles archive.
    window.fetch = async function (input, init) {
      try {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (typeof url === 'string' && url.startsWith('pmtiles://')) {
          // Expect URLs like: pmtiles:///sample_webp.pmtiles/{z}/{x}/{y}
          const m = url.match(/pmtiles:\/\/+[^\/]+\/(\d+)\/(\d+)\/(\d+)/);
          if (!m) throw new Error('pmtiles url parse failed: ' + url);
          const z = Number(m[1]);
          const x = Number(m[2]);
          const y = Number(m[3]);

          // Try multiple possible PMTiles API names (getZxy, getTile, get)
          let tileData = null;
          if (typeof pm.getZxy === 'function') {
            tileData = await pm.getZxy(z, x, y);
          } else if (typeof pm.getTile === 'function') {
            tileData = await pm.getTile(z, x, y);
          } else if (typeof pm.get === 'function') {
            tileData = await pm.get(z, x, y);
          }

          if (!tileData) throw new Error('tile not found in PMTiles');

          // tileData may be ArrayBuffer, Uint8Array, or an object {data:Uint8Array}
          let bytes = tileData;
          if (tileData.data) bytes = tileData.data;
          if (bytes instanceof Uint8Array) bytes = bytes.buffer;

          return new Response(bytes, { status: 200, headers: { 'Content-Type': 'application/octet-stream' } });
        }
      } catch (e) {
        console.warn('pmtiles fetch handler error:', e);
        // fall through to original fetch
      }
      return _origFetch(input, init);
    };

    // Now add a raster-dem source using pmtiles:// URLs
    const pmtilesUrl = `pmtiles:///sample_webp.pmtiles`;
    map.addSource('terrain-dem', {
      type: 'raster-dem',
      tiles: [pmtilesUrl + '/{z}/{x}/{y}'],
      tileSize: 256,
      maxzoom: 17
    });
    console.log('Registered pmtiles:// protocol (in-browser) and added terrain-dem source.');
  } catch (err) {
    console.warn('pmtiles handler not available, falling back to XYZ server. Run: pmtiles serve docs/sample_webp.pmtiles --port 3001 --cors "*"', err);
    map.addSource('terrain-dem', {
      type: 'raster-dem',
      tiles: [PMTILES_XYZ],
      tileSize: 256,
      maxzoom: 17
    });
  }

  map.setTerrain({ source: 'terrain-dem', exaggeration: 1.0 });
  map.addLayer({ id: 'hillshade', type: 'hillshade', source: 'terrain-dem' });
  map.addControl(new maplibregl.NavigationControl(), 'top-left');
});
