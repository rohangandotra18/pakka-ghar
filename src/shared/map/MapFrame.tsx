import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Pressable, View } from 'react-native';
import { C, R, T } from '@/design';
import type { MapCoreEvent, MapCoreState, MapCoreTheme } from './mapCore';
import type { MapViewProps } from './mapTypes';

/* The parts of MapView that are the same on phones and on the website: the colours, the state sent to the map, how its
   events reach the props, and the frame with the "Loading map…" / Retry overlay. */
export const MAP_THEME: MapCoreTheme = { accent: C.accent, ink: C.ink, line: C.line };

export function mapState(p: MapViewProps): MapCoreState {
  return {
    pins: p.pins ?? [], center: p.center, radiusKm: p.radiusKm, zoom: p.zoom, fit: p.fit, picked: p.picked ?? null,
    pick: !!p.onPick, selectedId: p.selectedId ?? null, cluster: !!p.cluster,
  };
}

/* Loading state: ready once the map has drawn its first frame; failed after a fatal error or 15 seconds without it. */
export function useMapStatus() {
  const [loads, setLoads] = useState(0);
  const [failed, setFailed] = useState<string | null>(null);
  /* bump to rebuild the map (Retry) */
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (loads) return;
    const t = setTimeout(() => setFailed(f => f ?? 'The map is taking too long to load.'), 15000);
    return () => clearTimeout(t);
  }, [loads, attempt]);
  const onReady = useCallback(() => { setLoads(n => n + 1); setFailed(null); }, []);
  const onFatal = useCallback((msg?: string) => setFailed(msg?.includes('WebGL') ? msg : "The map couldn't load. Check your connection."), []);
  const retry = useCallback(() => { setFailed(null); setLoads(0); setAttempt(a => a + 1); }, []);
  /* `loads` counts 'ready' events, so a phone web view that reloads gets its state sent again */
  return { ready: loads > 0, loads, failed, attempt, onReady, onFatal, retry };
}
export type MapStatus = ReturnType<typeof useMapStatus>;

export function handleMapEvent(e: MapCoreEvent, status: MapStatus, h: Pick<MapViewProps, 'onPick' | 'onPinPress' | 'onRegionChange'>) {
  if (e.type === 'ready') status.onReady();
  else if (e.type === 'pin') h.onPinPress?.(e.id);
  else if (e.type === 'pick') h.onPick?.({ lat: e.lat, lng: e.lng });
  else if (e.type === 'region') h.onRegionChange?.({ bounds: e.bounds, center: e.center, zoom: e.zoom, byUser: e.byUser });
  else if (e.type === 'error') {
    console.warn('[map]', e.msg);
    if (e.fatal) status.onFatal(e.msg);
  }
}

export function MapFrame({ height = 220, fill, picking, status, children }: { height?: number; fill?: boolean; picking: boolean; status: MapStatus; children: ReactNode }) {
  const { ready, failed, retry } = status;
  return (
    <View style={[fill ? { flex: 1 } : { height }, { borderRadius: R.lg, overflow: 'hidden', borderWidth: 1, borderColor: picking ? C.accent : C.line, backgroundColor: C.map }]}>
      {children}
      {!ready && (
        <View pointerEvents={failed ? 'auto' : 'none'} style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 16, backgroundColor: C.map }}>
          <T v="sm" style={{ textAlign: 'center' }}>{failed ?? 'Loading map…'}</T>
          {failed && <Pressable accessibilityRole="button" onPress={retry}
            style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface }}>
            <T v="smBold">Retry</T></Pressable>}
        </View>
      )}
    </View>
  );
}
