import { useMemo } from 'react';
import { View } from 'react-native';
import { MapView, type MapRegion } from '@/shared';
import { Btn, GENDER_COLOR, useWide } from '@/design';
import { inr, type Schemas } from '@/core/api';
import type { AreaOffer, Place } from './findState';
import { RADIUS_KM } from './findState';

const ZOOM = 15;
/* The map with the pins of the results and, when the person has moved it, the "Search this area" pill over its top. In area
   mode the camera is told the same centre and zoom as before and `fit` is off, so new pins never move it.
   On a wide screen it fills its pane edge to edge (`bare`: no border or corners) and the pill floats 16 px from the top. */
export function FindMap({ place, area, pgs, selectedId, offer, onPin, onRegion, onSearchArea }: {
  place: Place; area: boolean; pgs: Schemas['ListingOut'][]; selectedId: string | null; offer: AreaOffer;
  onPin: (id: string) => void; onRegion: (r: MapRegion) => void; onSearchArea: () => void;
}) {
  const wide = useWide();
  const center = useMemo(() => ({ lat: place.lat, lng: place.lng, label: place.name }), [place]);
  const pins = useMemo(() => pgs.map(p => ({
    id: p.id, lat: p.lat, lng: p.lng, label: '₹' + Math.round(p.rent_paise / 100000 * 10) / 10 + 'k', color: GENDER_COLOR[p.gender],
    title: `${p.name}, ${inr(p.rent_paise)} per bed`,
  })), [pgs]);
  const map = (
    <MapView height={wide ? undefined : 260} fill={wide} bare={wide} center={center} zoom={ZOOM} fit={!area} radiusKm={area ? undefined : RADIUS_KM} pins={pins}
      selectedId={selectedId} cluster onPinPress={onPin} onRegionChange={onRegion} />
  );
  const pill = offer !== 'none' && (
    <View pointerEvents="box-none" style={{ position: 'absolute', top: wide ? 16 : 10, left: 0, right: 0, alignItems: 'center' }}>
      <Btn small kind="secondary" label={offer === 'zoom' ? 'Zoom in to search this area' : 'Search this area'} disabled={offer === 'zoom'} onPress={onSearchArea} />
    </View>
  );
  if (!wide) return <View>{map}{pill}</View>;
  return (
    <View style={{ flex: 1 }}>
      {map}
      {pill}
    </View>
  );
}
