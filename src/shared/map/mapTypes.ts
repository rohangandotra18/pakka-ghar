export type LatLng = { lat: number; lng: number };
export type MapPin = LatLng & { id: string; label: string; color: string; title?: string };
export type Bounds = { west: number; south: number; east: number; north: number };
export type MapRegion = { bounds: Bounds; center: LatLng; zoom: number; byUser: boolean };

/* The props of MapView, the same on phones and on the website. */
export type MapViewProps = {
  height?: number;
  pins?: MapPin[];
  center?: LatLng & { label?: string };
  radiusKm?: number;
  zoom?: number;
  /* with fit the camera frames every pin and the centre; without it, it moves only when `center` or `zoom` change */
  fit?: boolean;
  picked?: LatLng | null;
  onPick?: (ll: LatLng) => void;
  onPinPress?: (id: string) => void;
  /* this pin is drawn highlighted and above the others */
  selectedId?: string | null;
  /* called once each time the map comes to rest; byUser is true when the person moved it */
  onRegionChange?: (r: MapRegion) => void;
  /* group pins that would overlap into a count; pressing it zooms in */
  cluster?: boolean;
  /* take all the height the parent gives (flex: 1) instead of `height` */
  fill?: boolean;
};
