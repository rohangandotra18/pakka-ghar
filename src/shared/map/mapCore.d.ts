/* Types for mapCore.js (the map's behaviour, shared by the website and the phone web view). */
import type { LatLng, MapPin, Bounds } from './mapTypes';

export type MapCoreState = {
  pins?: MapPin[];
  center?: (LatLng & { label?: string }) | null;
  radiusKm?: number;
  zoom?: number;
  fit?: boolean;
  picked?: LatLng | null;
  /* true when the owner can place a pin by pressing the map */
  pick?: boolean;
  selectedId?: string | null;
  cluster?: boolean;
};
export type MapCoreEvent =
  | { type: 'ready' }
  | { type: 'pin'; id: string }
  | { type: 'pick'; lat: number; lng: number }
  | { type: 'region'; bounds: Bounds; center: LatLng; zoom: number; byUser: boolean }
  | { type: 'error'; fatal: boolean; msg: string };
export type MapCoreTheme = { accent: string; ink: string; line: string };
export type MapCore = { setState(state: MapCoreState): void; destroy(): void };

export function createMapCore(
  maplibregl: typeof import('maplibre-gl'),
  container: HTMLElement,
  emit: (event: MapCoreEvent) => void,
  theme?: MapCoreTheme,
): MapCore;
