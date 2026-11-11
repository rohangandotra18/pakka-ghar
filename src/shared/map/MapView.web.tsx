import { useEffect, useRef } from 'react';
import { MAP_THEME, MapFrame, handleMapEvent, mapState, useMapStatus } from './MapFrame';
import { createMapCore, type MapCore } from './mapCore';
import type { MapViewProps } from './mapTypes';

export type { Bounds, LatLng, MapPin, MapRegion } from './mapTypes';
export { kmBetween } from './geo';

/* The website's map: the same behaviour (mapCore.js) and the same MapLibre engine as the apps, drawn straight into the
   page (the apps run it inside a web view). MapLibre's code and styles load only when a map opens. */
let cssAdded = false;

export function MapView(props: MapViewProps) {
  const { height, fill, onPick } = props;
  const box = useRef<HTMLDivElement | null>(null);
  const core = useRef<MapCore | null>(null);
  const status = useMapStatus();
  const handlers = useRef({ props, status });
  const state = mapState(props);
  const json = JSON.stringify(state);
  const latest = useRef(state);
  useEffect(() => { handlers.current = { props, status }; latest.current = state; });

  useEffect(() => {
    let gone = false;
    Promise.all([import('maplibre-gl'), import('./mapCss.generated')]).then(([m, css]) => {
      if (gone || !box.current) return;
      if (!cssAdded) { const st = document.createElement('style'); st.textContent = css.MAPLIBRE_CSS; document.head.appendChild(st); cssAdded = true; }
      const maplibregl = (m as unknown as { default?: typeof import('maplibre-gl') }).default ?? m;
      const c = createMapCore(maplibregl, box.current, e => handleMapEvent(e, handlers.current.status, handlers.current.props), MAP_THEME);
      c.setState(latest.current);
      core.current = c;
    }).catch(() => { if (!gone) handlers.current.status.onFatal(); });
    return () => { gone = true; core.current?.destroy(); core.current = null; };
  }, [status.attempt]);

  useEffect(() => { core.current?.setState(latest.current); }, [json]);

  return (
    <MapFrame height={height} fill={fill} picking={!!onPick} status={status}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
        <div ref={box} style={{ width: '100%', height: '100%', cursor: onPick ? 'crosshair' : 'grab' }} aria-label={onPick ? 'Map. Click your building to place the pin.' : 'Map of PGs'} />
      </div>
    </MapFrame>
  );
}
