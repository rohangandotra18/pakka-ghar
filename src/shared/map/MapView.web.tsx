import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
import { C, R, T } from '@/design';
import { MAPLIBRE_CSS } from './mapEngine.generated';
import type { LatLng, MapPin } from './MapView';

/* The website's map: the same MapLibre engine and OpenFreeMap style as the apps, drawn straight into the page
   (the apps run it inside a web view). Same props, same behaviour. */
type Props = {
  height?: number; pins?: MapPin[]; center?: LatLng & { label?: string }; radiusKm?: number; zoom?: number; fit?: boolean;
  picked?: LatLng | null; onPick?: (ll: LatLng) => void; onPinPress?: (id: string) => void;
};

type ML = typeof import('maplibre-gl');

function circle(c: LatLng, km: number) {
  const pts: [number, number][] = [];
  const dLat = km / 110.574, dLng = km / (111.32 * Math.cos((c.lat * Math.PI) / 180));
  for (let i = 0; i <= 64; i++) { const a = (i / 64) * 2 * Math.PI; pts.push([c.lng + dLng * Math.cos(a), c.lat + dLat * Math.sin(a)]); }
  return { type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [pts] } };
}

let cssAdded = false;

export function MapView({ height = 220, pins = [], center, radiusKm, zoom, fit, picked, onPick, onPinPress }: Props) {
  const box = useRef<HTMLDivElement | null>(null);
  const map = useRef<import('maplibre-gl').Map | null>(null);
  const lib = useRef<ML | null>(null);
  const markers = useRef<import('maplibre-gl').Marker[]>([]);
  const pickMk = useRef<import('maplibre-gl').Marker | null>(null);
  const handlers = useRef({ onPick, onPinPress });
  const lastCam = useRef('');
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => { handlers.current = { onPick, onPinPress }; });

  useEffect(() => {
    if (!cssAdded) { const st = document.createElement('style'); st.textContent = MAPLIBRE_CSS; document.head.appendChild(st); cssAdded = true; }
    let gone = false;
    import('maplibre-gl').then(m => {
      if (gone || !box.current) return;
      const maplibregl = (m as unknown as { default?: ML }).default ?? m;
      lib.current = maplibregl;
      const mp = new maplibregl.Map({ container: box.current, style: 'https://tiles.openfreemap.org/styles/positron', center: [76.772, 30.755],
        zoom: 13.5, attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false, touchPitch: false, fadeDuration: 0 });
      mp.touchZoomRotate.disableRotation();
      mp.on('load', () => {
        mp.addSource('ring', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        mp.addLayer({ id: 'ring-fill', type: 'fill', source: 'ring', paint: { 'fill-color': C.accent, 'fill-opacity': 0.07 } });
        mp.addLayer({ id: 'ring-line', type: 'line', source: 'ring', paint: { 'line-color': C.accent, 'line-width': 1.4, 'line-dasharray': [2, 2] } });
        setReady(true);
      });
      mp.on('click', e => handlers.current.onPick?.({ lat: e.lngLat.lat, lng: e.lngLat.lng }));
      mp.on('error', e => { if (!mp.loaded()) setFailed("The map couldn't load. Check your connection."); console.warn('[map]', e?.error?.message); });
      map.current = mp;
    }).catch(() => setFailed("The map couldn't load."));
    return () => { gone = true; map.current?.remove(); map.current = null; };
  }, []);

  const state = JSON.stringify({ pins, center, radiusKm, zoom, fit, picked });
  useEffect(() => {
    const mp = map.current, m = lib.current;
    if (!ready || !mp || !m) return;
    markers.current.forEach(x => x.remove());
    markers.current = pins.map(p => {
      const el = document.createElement('div');
      el.style.cssText = `display:flex;align-items:center;gap:5px;background:#fff;border:1px solid ${C.line};border-radius:999px;padding:4px 9px;font:700 12px system-ui,sans-serif;color:${C.ink};white-space:nowrap;box-shadow:0 1px 2px rgba(17,23,20,.12);cursor:pointer`;
      el.innerHTML = `<i style="width:7px;height:7px;border-radius:50%;display:block;background:${p.color}"></i>${p.label.replace(/</g, '&lt;')}`;
      el.addEventListener('click', ev => { ev.stopPropagation(); handlers.current.onPinPress?.(p.id); });
      return new m.Marker({ element: el, anchor: 'bottom' }).setLngLat([p.lng, p.lat]).addTo(mp);
    });
    if (center && (radiusKm || center.label)) {
      const el = document.createElement('div');
      el.style.cssText = `width:12px;height:12px;border-radius:50%;background:${C.ink};border:2px solid #fff`;
      markers.current.push(new m.Marker({ element: el }).setLngLat([center.lng, center.lat]).addTo(mp));
    }
    (mp.getSource('ring') as import('maplibre-gl').GeoJSONSource | undefined)?.setData(center && radiusKm ? circle(center, radiusKm) : { type: 'FeatureCollection', features: [] });
    if (picked) {
      if (!pickMk.current) {
        const el = document.createElement('div');
        el.style.cssText = `width:26px;height:26px;border-radius:50%;background:${C.accent};border:3px solid #fff;box-shadow:0 1px 3px rgba(17,23,20,.3)`;
        pickMk.current = new m.Marker({ element: el }).setLngLat([picked.lng, picked.lat]).addTo(mp);
      } else pickMk.current.setLngLat([picked.lng, picked.lat]);
    } else if (pickMk.current) { pickMk.current.remove(); pickMk.current = null; }
    const pts: [number, number][] = pins.map(p => [p.lng, p.lat]);
    if (center) pts.push([center.lng, center.lat]);
    const cam = JSON.stringify([pts, zoom, !!fit]);   // move only when what's framed changes
    if (cam === lastCam.current) return;
    lastCam.current = cam;
    if (fit && pts.length > 1) {
      const b = new m.LngLatBounds(pts[0], pts[0]);
      pts.forEach(q => b.extend(q));
      mp.fitBounds(b, { padding: { top: 44, bottom: 30, left: 44, right: 44 }, maxZoom: zoom ?? 15.5, duration: 0 });
    } else if (center) mp.jumpTo({ center: [center.lng, center.lat], zoom: zoom ?? 14 });
  }, [ready, state]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <View style={{ height, borderRadius: R.lg, overflow: 'hidden', borderWidth: 1, borderColor: onPick ? C.accent : C.line, backgroundColor: C.map }}>
      <div ref={box} style={{ width: '100%', height: '100%', cursor: onPick ? 'crosshair' : 'grab' }} aria-label={onPick ? 'Map. Click your building to place the pin.' : 'Map of PGs'} />
      {!ready && <View pointerEvents="none" style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' }}><T v="sm">{failed ?? 'Loading map…'}</T></View>}
    </View>
  );
}

export function kmBetween(a: LatLng, b: LatLng) {
  const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLng = (b.lng - a.lng) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}
