/* The map's behaviour, written once. The website imports this file directly; phones run a GENERATED COPY of it
   inside a web view (src/shared/map/mapEngine.generated.ts). After editing this file run `npm run map:engine`
   (it also runs on npm install). Keep it plain ES2017 with no imports and a single `export function createMapCore`:
   scripts/build-map-engine.js turns that one export into a global for the web view and fails if the shape differs.

   createMapCore(maplibregl, container, emit, theme) -> { setState(state), destroy() }
   - state: { pins, center, radiusKm, zoom, fit, picked, pick, selectedId, cluster } (see MapView props).
   - emit({type}): 'ready', 'pin' {id}, 'pick' {lat,lng}, 'region' {bounds,center,zoom,byUser},
     'error' {fatal,msg}.
   - theme: { accent, ink, line } colours. */
export function createMapCore(maplibregl, container, emit, theme) {
  const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';
  const FONT = "700 12px -apple-system,Roboto,'Helvetica Neue',system-ui,sans-serif";
  const doc = container.ownerDocument;
  const th = { accent: '#0E6B50', ink: '#111714', line: '#E2E7E3' };
  if (theme) { Object.keys(th).forEach(k => { if (theme[k]) th[k] = theme[k]; }); }

  let map = null;
  let styleReady = false, ready = false, destroyed = false, first = true;
  let pending = null;
  let pickOn = false, clusterOn = false, selectedId = null;
  let lastFitKey = null, lastCenterKey = null, lastRingKey = '', lastHereKey = '', lastPinsKey = null;
  let hereMarker = null, pickMarker = null;
  let pinsById = {};
  const markers = new Map(); // key -> { marker, el, sig, pinId }

  try {
    map = new maplibregl.Map({
      container, style: STYLE_URL, center: [76.772, 30.755], zoom: 13.5,
      attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false, touchPitch: false, fadeDuration: 0,
    });
  } catch (err) {
    emit({ type: 'error', fatal: true, msg: String((err && err.message) || err) });
    return { setState() {}, destroy() {} };
  }
  /* rotation and pitch stay off for touch, mouse and keyboard */
  map.touchZoomRotate.disableRotation();
  if (map.keyboard && map.keyboard.disableRotation) map.keyboard.disableRotation();

  function circle(c, km) {
    const pts = [], dLat = km / 110.574, dLng = km / (111.32 * Math.cos(c.lat * Math.PI / 180));
    for (let i = 0; i <= 64; i++) { const a = i / 64 * 2 * Math.PI; pts.push([c.lng + dLng * Math.cos(a), c.lat + dLat * Math.sin(a)]); }
    return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [pts] } };
  }
  const EMPTY = { type: 'FeatureCollection', features: [] };

  /* ---- elements (text is always set with textContent, never as markup) ---- */
  function onPress(el, fn) {
    el.addEventListener('click', ev => { ev.stopPropagation(); fn(); });
    el.addEventListener('keydown', ev => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); ev.stopPropagation(); fn(); }
    });
    el.addEventListener('focus', () => { el.style.outline = '2px solid ' + th.accent; el.style.outlineOffset = '2px'; });
    el.addEventListener('blur', () => { el.style.outline = 'none'; });
  }
  function paintPin(el, selected) {
    el.style.background = selected ? th.accent : '#fff';
    el.style.color = selected ? '#fff' : th.ink;
    el.style.borderColor = selected ? th.accent : th.line;
    el.style.zIndex = selected ? '10' : '1';
    if (selected) el.setAttribute('aria-current', 'true'); else el.removeAttribute('aria-current');
    const dot = el.firstChild;
    if (dot) dot.style.boxShadow = selected ? '0 0 0 1.5px #fff' : 'none';
  }
  function makePinEl(p) {
    const el = doc.createElement('div');
    el.className = 'pg-pin';
    el.style.cssText = 'display:flex;align-items:center;gap:5px;border:1px solid ' + th.line + ';border-radius:999px;padding:4px 9px;font:' + FONT +
      ';white-space:nowrap;box-shadow:0 1px 2px rgba(17,23,20,.12);cursor:pointer;-webkit-tap-highlight-color:transparent';
    const name = p.title || p.label;
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    el.setAttribute('aria-label', name);
    el.setAttribute('title', name);
    const dot = doc.createElement('i');
    dot.style.cssText = 'width:7px;height:7px;border-radius:50%;display:block;flex:none';
    dot.style.background = p.color;
    const text = doc.createElement('span');
    text.textContent = p.label;
    el.appendChild(dot);
    el.appendChild(text);
    onPress(el, () => emit({ type: 'pin', id: p.id }));
    return el;
  }
  function makeClusterEl(count, lng, lat, clusterId) {
    const el = doc.createElement('div');
    el.className = 'pg-cluster';
    el.style.cssText = 'min-width:36px;height:36px;box-sizing:border-box;padding:0 6px;border-radius:999px;display:flex;align-items:center;justify-content:center;background:' +
      th.ink + ';color:#fff;border:3px solid #fff;font:' + FONT + ';box-shadow:0 1px 3px rgba(17,23,20,.35);cursor:pointer;z-index:2;-webkit-tap-highlight-color:transparent';
    const label = count + ' PGs, zoom in';
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    el.setAttribute('aria-label', label);
    el.setAttribute('title', label);
    el.textContent = String(count);
    onPress(el, () => {
      const src = map.getSource('pins');
      if (!src) return;
      src.getClusterExpansionZoom(clusterId).then(z => {
        if (!destroyed) map.easeTo({ center: [lng, lat], zoom: z, duration: 450 });
      }).catch(() => {});
    });
    return el;
  }
  function makeHereEl(label) {
    const el = doc.createElement('div');
    el.style.cssText = 'width:12px;height:12px;border-radius:50%;box-sizing:border-box;border:2px solid #fff;box-shadow:0 0 0 1px rgba(17,23,20,.2);pointer-events:none';
    el.style.background = th.ink;
    if (label) el.setAttribute('title', label);
    return el;
  }
  function makePickEl() {
    const el = doc.createElement('div');
    el.style.cssText = 'display:flex;flex-direction:column;align-items:center;pointer-events:none';
    const head = doc.createElement('b');
    head.style.cssText = 'width:30px;height:30px;box-sizing:border-box;border-radius:50%;border:3px solid #fff;display:block;box-shadow:0 1px 3px rgba(17,23,20,.3)';
    head.style.background = th.accent;
    const stem = doc.createElement('s');
    stem.style.cssText = 'width:3px;height:9px;display:block;text-decoration:none';
    stem.style.background = th.accent;
    el.appendChild(head);
    el.appendChild(stem);
    return el;
  }

  /* ---- markers: pins and clusters share one keyed set, so only what changed is rebuilt ---- */
  function reconcile(desired) {
    const keep = {};
    desired.forEach(d => {
      keep[d.key] = true;
      let r = markers.get(d.key);
      if (r && r.sig !== d.sig) { r.marker.remove(); markers.delete(d.key); r = null; }
      if (!r) {
        const el = d.build();
        const marker = new maplibregl.Marker({ element: el, anchor: d.anchor }).setLngLat([d.lng, d.lat]).addTo(map);
        r = { marker, el, sig: d.sig, pinId: d.pinId };
        markers.set(d.key, r);
        if (d.pinId != null) paintPin(el, d.pinId === selectedId);
      }
    });
    markers.forEach((r, key) => { if (!keep[key]) { r.marker.remove(); markers.delete(key); } });
  }
  function paintSelection() {
    markers.forEach(r => { if (r.pinId != null) paintPin(r.el, r.pinId === selectedId); });
  }
  function pinDesc(p) {
    return {
      key: 'p:' + p.id, pinId: p.id, lng: p.lng, lat: p.lat, anchor: 'bottom',
      sig: [p.lng, p.lat, p.label, p.color, p.title || ''].join('|'), build: () => makePinEl(p),
    };
  }
  function syncPlainPins(pins) { reconcile(pins.map(pinDesc)); }
  /* clustered: show what the clustering source reports for the current view (MapLibre's "HTML clusters" approach) */
  function syncClusters() {
    if (!ready || !clusterOn || destroyed || !map.getSource('pins') || !map.isSourceLoaded('pins')) return;
    const seen = {}, desired = [];
    map.querySourceFeatures('pins').forEach(f => {
      const pr = f.properties || {}, c = f.geometry.coordinates;
      if (pr.cluster) {
        const key = 'c:' + pr.cluster_id + ':' + pr.point_count;
        if (seen[key]) return;
        seen[key] = true;
        desired.push({ key, lng: c[0], lat: c[1], anchor: 'center', sig: key, build: () => makeClusterEl(pr.point_count, c[0], c[1], pr.cluster_id) });
      } else {
        const p = pinsById[pr.id];
        if (!p || seen['p:' + p.id]) return;
        seen['p:' + p.id] = true;
        desired.push(pinDesc(p));
      }
    });
    reconcile(desired);
  }

  /* ---- camera: fit follows the set of points; otherwise only `center` / `zoom` move it, never pins or picks ---- */
  function placeCamera(s) {
    const pts = (s.pins || []).map(p => [p.lng, p.lat]);
    if (s.center) pts.push([s.center.lng, s.center.lat]);
    const centerKey = s.center ? JSON.stringify([s.center.lat, s.center.lng, s.zoom]) : null;
    const fitKey = JSON.stringify([pts, s.zoom]);
    let move = null;
    if (s.fit) {
      if (first || fitKey !== lastFitKey) move = pts.length > 1 ? 'fit' : (s.center ? 'center' : null);
      lastFitKey = fitKey;
    } else {
      if (centerKey && (first || centerKey !== lastCenterKey)) move = 'center';
      lastFitKey = null;
    }
    lastCenterKey = centerKey;
    const dur = first ? 0 : 450;
    if (move === 'fit') {
      let w = 180, so = 90, e = -180, n = -90;
      pts.forEach(q => { w = Math.min(w, q[0]); e = Math.max(e, q[0]); so = Math.min(so, q[1]); n = Math.max(n, q[1]); });
      map.fitBounds([[w, so], [e, n]], { padding: { top: 70, bottom: 56, left: 70, right: 70 }, maxZoom: s.zoom || 15.5, duration: dur });
    } else if (move === 'center') {
      const o = { center: [s.center.lng, s.center.lat], zoom: s.zoom || 14 };
      if (first) map.jumpTo(o); else map.easeTo({ center: o.center, zoom: o.zoom, duration: dur });
    }
    return move !== null;
  }

  function region(byUser) {
    const b = map.getBounds(), c = map.getCenter();
    emit({
      type: 'region', byUser,
      bounds: { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() },
      center: { lat: c.lat, lng: c.lng }, zoom: map.getZoom(),
    });
  }

  function apply(s) {
    pickOn = !!s.pick;
    selectedId = s.selectedId == null ? null : String(s.selectedId);
    const canvas = map.getCanvas && map.getCanvas();
    if (canvas) canvas.style.cursor = pickOn ? 'crosshair' : '';

    const pins = s.pins || [];
    pinsById = {};
    pins.forEach(p => { pinsById[p.id] = p; });
    const wantCluster = !!s.cluster;
    const pinsKey = JSON.stringify(pins.map(p => [p.id, p.lng, p.lat]));
    if (wantCluster !== clusterOn) {
      clusterOn = wantCluster;
      markers.forEach(r => r.marker.remove());
      markers.clear();
      lastPinsKey = null;
    }
    if (clusterOn) {
      if (pinsKey !== lastPinsKey) {
        lastPinsKey = pinsKey;
        map.getSource('pins').setData({
          type: 'FeatureCollection',
          features: pins.map(p => ({ type: 'Feature', properties: { id: p.id }, geometry: { type: 'Point', coordinates: [p.lng, p.lat] } })),
        });
      }
      syncClusters();
    } else {
      if (lastPinsKey !== '') { lastPinsKey = ''; map.getSource('pins').setData(EMPTY); }
      syncPlainPins(pins);
    }
    paintSelection();

    const ringKey = s.center && s.radiusKm ? JSON.stringify([s.center.lat, s.center.lng, s.radiusKm]) : '';
    if (ringKey !== lastRingKey) {
      lastRingKey = ringKey;
      map.getSource('ring').setData(ringKey ? circle(s.center, s.radiusKm) : EMPTY);
    }
    const hereKey = s.center && (s.radiusKm || s.center.label) ? JSON.stringify([s.center.lat, s.center.lng, s.center.label || '']) : '';
    if (hereKey !== lastHereKey) {
      lastHereKey = hereKey;
      if (hereMarker) { hereMarker.remove(); hereMarker = null; }
      if (hereKey) hereMarker = new maplibregl.Marker({ element: makeHereEl(s.center.label) }).setLngLat([s.center.lng, s.center.lat]).addTo(map);
    }
    if (s.picked) {
      if (!pickMarker) pickMarker = new maplibregl.Marker({ element: makePickEl(), anchor: 'bottom' }).setLngLat([s.picked.lng, s.picked.lat]).addTo(map);
      else pickMarker.setLngLat([s.picked.lng, s.picked.lat]);
    } else if (pickMarker) { pickMarker.remove(); pickMarker = null; }

    const moved = placeCamera(s);
    if (first) {
      first = false;
      if (!moved) region(false); // a move's own `moveend` reports the first region; otherwise report it here
    }
  }

  /* The style is usable once a source can be added; the map is "ready" at its first drawn frame after that, so we do not
     wait for every tile and font (MapLibre's `load` event does). */
  function setupStyle() {
    if (styleReady || destroyed) return;
    try {
      map.addSource('ring', { type: 'geojson', data: EMPTY });
      map.addSource('pins', { type: 'geojson', data: EMPTY, cluster: true, clusterRadius: 50, clusterMaxZoom: 16 });
    } catch (_e) {
      if (map.getSource && map.getSource('ring')) map.removeSource('ring');
      return; // style JSON not loaded yet; the next `styledata` retries
    }
    map.addLayer({ id: 'ring-fill', type: 'fill', source: 'ring', paint: { 'fill-color': th.accent, 'fill-opacity': 0.07 } });
    map.addLayer({ id: 'ring-line', type: 'line', source: 'ring', paint: { 'line-color': th.accent, 'line-width': 1.4, 'line-dasharray': [2, 2] } });
    /* invisible, but a source only loads tiles when a layer uses it, and the cluster markers read those tiles */
    map.addLayer({ id: 'pins-probe', type: 'circle', source: 'pins', paint: { 'circle-radius': 1, 'circle-opacity': 0 } });
    styleReady = true;
  }
  function onRender() {
    if (!styleReady || ready || destroyed) return;
    ready = true;
    const a = container.querySelector && container.querySelector('.maplibregl-ctrl-attrib');
    if (a) a.classList.remove('maplibregl-compact-show');
    emit({ type: 'ready' });
    if (pending) { const p = pending; pending = null; apply(p); }
  }
  map.on('styledata', setupStyle);
  map.on('render', onRender);
  map.on('click', e => { if (ready && pickOn) emit({ type: 'pick', lat: e.lngLat.lat, lng: e.lngLat.lng }); });
  /* `originalEvent` is set by MapLibre only for moves the person caused (drag, pinch, wheel, double-tap, keyboard) */
  map.on('moveend', e => { if (ready) region(!!(e && e.originalEvent)); });
  map.on('move', syncClusters);
  map.on('moveend', syncClusters);
  map.on('sourcedata', e => { if (e && e.sourceId === 'pins') syncClusters(); });
  map.on('error', e => {
    emit({ type: 'error', fatal: !ready, msg: String((e && e.error && e.error.message) || e) });
  });

  return {
    setState(s) {
      if (destroyed || !s) return;
      if (!ready) { pending = s; return; }
      apply(s);
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      markers.forEach(r => r.marker.remove());
      markers.clear();
      if (hereMarker) hereMarker.remove();
      if (pickMarker) pickMarker.remove();
      hereMarker = pickMarker = null;
      map.remove();
    },
  };
}
