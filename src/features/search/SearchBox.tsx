import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, TextInput, View } from 'react-native';
import { Card, T, C, F, R, GENDER_COLOR, Dot } from '@/design';
import { inr, type Schemas } from '@/core/api';
import { MIN_CHARS, useTypeahead } from './useTypeahead';
import { placeSubtitle, type Place } from './findState';

type PlaceHit = Schemas['PlaceOut'];
const asPlace = (p: PlaceHit): Place => ({ name: p.name, lat: p.lat, lng: p.lng });

/* The search box and, while there is something typed, the places and PGs it finds directly under it. */
export function SearchBox({ value, onChange, onPick }: { value: string; onChange: (t: string) => void; onPick: (p: Place) => void }) {
  /* set by typing, cleared by choosing a result or clearing, so putting a place's name in the box doesn't search again */
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const shown = open && value.trim().length >= MIN_CHARS;
  const found = useTypeahead(shown ? value : '');
  const pick = (p: PlaceHit) => { setOpen(false); onChange(p.name); onPick(asPlace(p)); };
  const type = (t: string) => { setOpen(true); onChange(t); };
  return (
    <View style={{ gap: 8 }}>
      {/* our own clear button: iOS's built-in one doesn't exist on Android */}
      <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderWidth: 1, borderColor: focused ? C.accent : C.line, borderRadius: 12 }}>
        <TextInput allowFontScaling={false} value={value} onChangeText={type} accessibilityLabel="Search a sector, college or PG"
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          onSubmitEditing={() => { const first = found?.places[0]; if (first) pick(first); }}
          placeholder="Search a sector, college or PG" placeholderTextColor={C.muted} returnKeyType="search" autoCorrect={false}
          underlineColorAndroid="transparent" selectionColor={C.accent}
          style={{ flex: 1, paddingHorizontal: 12, paddingVertical: 12, fontFamily: F.semi, fontSize: 15, color: C.ink }} />
        {value ? <Pressable onPress={() => { setOpen(false); onChange(''); }} hitSlop={8} accessibilityRole="button" accessibilityLabel="Clear search" style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center', marginRight: 10 }}><T v="smBold" style={{ fontSize: 12, color: C.muted }}>✕</T></Pressable> : null}
      </View>
      {shown && <Results found={found} text={value.trim()} onPlace={pick} />}
    </View>
  );
}

function Results({ found, text, onPlace }: { found: ReturnType<typeof useTypeahead>; text: string; onPlace: (p: PlaceHit) => void }) {
  if (!found) return <Card><T v="sm">Searching…</T></Card>;
  if (found.failed) return <Card><T v="sm">Couldn’t search just now. Check your connection and try again.</T></Card>;
  if (!found.places.length && !found.pgs.length) return <Card><T v="sm">Nothing found for “{text}”. Try a sector number or a college name.</T></Card>;
  return (
    <Card style={{ padding: 6, gap: 0 }}>
      {found.places.length > 0 && <T v="label" style={{ paddingHorizontal: 8, paddingTop: 8, paddingBottom: 2 }}>Places</T>}
      {found.places.map(p => (
        <Pressable key={`place-${p.id}`} onPress={() => onPlace(p)} accessibilityRole="button" accessibilityLabel={`${p.name}, ${placeSubtitle(p)}`} style={({ pressed }) => ({ paddingHorizontal: 8, paddingVertical: 9, borderRadius: R.sm, backgroundColor: pressed ? C.surface2 : 'transparent' })}>
          <T v="bodyBold">{p.name}</T>
          <T v="sm">{placeSubtitle(p)}</T>
        </Pressable>
      ))}
      {found.pgs.length > 0 && <T v="label" style={{ paddingHorizontal: 8, paddingTop: 10, paddingBottom: 2 }}>PGs</T>}
      {found.pgs.map(p => (
        <Pressable key={`pg-${p.id}`} onPress={() => router.push(`/pg/${p.id}`)} accessibilityRole="button" accessibilityLabel={`${p.name}, ${p.area}, ${inr(p.rent_paise)} per bed`} style={({ pressed }) => ({ paddingHorizontal: 8, paddingVertical: 9, borderRadius: R.sm, backgroundColor: pressed ? C.surface2 : 'transparent' })}>
          <T v="bodyBold">{p.name}</T>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Dot color={GENDER_COLOR[p.gender]} /><T v="sm">{p.area} · {inr(p.rent_paise)} /bed</T></View>
        </Pressable>
      ))}
    </Card>
  );
}
