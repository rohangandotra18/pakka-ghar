import { useMemo, useState } from 'react';
import { View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import { Chip, Chips, T, C, GENDER_COLOR, R, SP } from '@/design';
import { MapView } from '@/shared';
import { inr } from '@/core/api';
import { PlaceSearchBox, findHref, usePopularPlaces, type Place } from '@/features/search';
import { MAP_LIMIT, useMapListings } from './useHomeListings';
import { Container, TextLink } from './parts';

/* Chandigarh, for the map's camera until there are pins to frame */
const CHANDIGARH = { lat: 30.7333, lng: 76.7794 };

/* "1 verified PG listed right now"; "200+" when the response is full; null while loading or when the request failed */
export function countLine(n: number | undefined): string | null {
  if (n === undefined) return null;
  if (n === 0) return 'PGs appear here as owners list them.';
  if (n >= MAP_LIMIT) return `${MAP_LIMIT}+ verified PGs listed right now`;
  return `${n} verified ${n === 1 ? 'PG' : 'PGs'} listed right now`;
}

/* Hero: the pitch and the search at the left, every PG on a map at the right. The search results open under the box and
   push the links down; the map is a separate column, so they never cover it. */
export function HomeHero() {
  const narrow = useWindowDimensions().width < 1100;
  return (
    <Container style={{ paddingTop: 32 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: narrow ? 32 : 48, minHeight: 460 }}>
        <View style={{ flex: 5, minWidth: 0, gap: SP.lg }}><Pitch /></View>
        <View style={{ flex: 7, minWidth: 0 }}><HeroMap /></View>
      </View>
    </Container>
  );
}

function Pitch() {
  const [text, setText] = useState('');
  const popular = usePopularPlaces().slice(0, 4);
  const go = (p: Place) => router.push(findHref(p));
  return (
    <>
      <T v="label" style={{ color: C.accent, fontSize: 13, letterSpacing: 0.4 }}>Chandigarh · Mohali · Panchkula</T>
      <View accessibilityRole="header" aria-level={1}><T v="display">Find a PG you can trust</T></View>
      <T style={{ fontSize: 16, lineHeight: 24, color: C.muted, maxWidth: 420 }}>Verified owners, real rent per bed, and your rent, electricity and agreement in one place. Free for everyone. No cash, ever.</T>
      <PlaceSearchBox value={text} onChange={setText} onPick={go} />
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: SP.sm }}>
        <T v="smBold" style={{ color: C.muted }}>Popular:</T>
        <View style={{ flex: 1, minWidth: 0 }}><Chips>{popular.map(p => <Chip key={p.name} label={p.name} onPress={() => go(p)} />)}</Chips></View>
      </View>
      <TextLink label="See every PG on the map" onPress={() => router.push('/find')} />
    </>
  );
}

function HeroMap() {
  const { list } = useMapListings();
  const pins = useMemo(() => (list ?? []).map(p => ({
    id: p.id, lat: p.lat, lng: p.lng, label: '₹' + Math.round(p.rent_paise / 100000 * 10) / 10 + 'k', color: GENDER_COLOR[p.gender],
    title: `${p.name}, ${inr(p.rent_paise)} per bed`,
  })), [list]);
  const line = countLine(list?.length);
  return (
    <View style={{ gap: SP.sm }}>
      <View style={{ height: 460, borderRadius: R.lg, borderWidth: 1, borderColor: C.line, overflow: 'hidden', backgroundColor: C.map }}>
        <MapView height={458} bare cluster fit center={CHANDIGARH} zoom={11} pins={pins} onPinPress={id => router.push(`/pg/${id}`)} />
      </View>
      {line ? <T v="sm">{line}</T> : <View style={{ height: 18 }} />}
    </View>
  );
}
