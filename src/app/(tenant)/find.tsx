import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, TextInput, View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { kmBetween, MapView } from '@/components/MapView';
import { Badge, Btn, Card, Chip, Chips, Dot, Screen, T } from '@/components/ui';
import { PGS } from '@/lib/data';
import { pinOf, useStore } from '@/lib/store';
import { C, F, GENDER_COLOR, R, rupees } from '@/lib/theme';

/* Places people search from. */
const NEAR = [
  { name: 'PGIMER', lat: 30.7649, lng: 76.7757 },
  { name: 'Panjab University', lat: 30.7605, lng: 76.766 },
  { name: 'Sector 17', lat: 30.7412, lng: 76.7788 },
];
const RADIUS_KM = 3;

export default function Find() {
  const { s } = useStore();
  const [near, setNear] = useState(NEAR[0]);
  const [girls, setGirls] = useState(false);
  const [q, setQ] = useState('');
  const query = q.trim().toLowerCase();
  const list = PGS
    .filter(p => !girls || p.gender === 'Girls')
    .filter(p => !query || `${p.name} ${p.area} ${p.gender}`.toLowerCase().includes(query))
    .map(p => { const at = pinOf(p, s.pins); return { p, at, km: Math.max(0.1, Math.round(kmBetween(at, near) * 10) / 10) }; })
    .filter(x => x.km <= RADIUS_KM)
    .sort((a, b) => a.km - b.km);
  const pick = (n: (typeof NEAR)[number]) => { setNear(n); setQ(''); };
  return (
    <Screen>
      <AppBar />
      <T v="h2">Where do you study or work?</T>
      {/* our own clear button: iOS's built-in one doesn't exist on Android */}
      <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: 12 }}>
        <TextInput allowFontScaling={false} value={q} onChangeText={t => { setQ(t); /* switch the place only on a full name, so typing 'sector 24' doesn't jump to Sector 17 */ const hit = NEAR.find(n => n.name.toLowerCase() === t.trim().toLowerCase()); if (hit) setNear(hit); }}
          placeholder="Search a PG, sector or college" placeholderTextColor={C.muted} returnKeyType="search" autoCorrect={false}
          underlineColorAndroid="transparent" selectionColor={C.accent}
          style={{ flex: 1, paddingHorizontal: 12, paddingVertical: 12, fontFamily: F.semi, fontSize: 15, color: C.ink }} />
        {q ? <Pressable onPress={() => setQ('')} hitSlop={8} accessibilityRole="button" accessibilityLabel="Clear search" style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center', marginRight: 10 }}><T v="smBold" style={{ fontSize: 12, color: C.muted }}>✕</T></Pressable> : null}
      </View>
      <Chips>{NEAR.map(n => <Chip key={n.name} label={n.name} on={near.name === n.name} onPress={() => pick(n)} />)}<Chip label="Girls only" on={girls} onPress={() => setGirls(!girls)} /></Chips>
      <MapView height={260} center={{ ...near, label: near.name }} fit zoom={15} pins={list.map(({ p, at }) => ({ id: p.id, ...at, label: '₹' + p.rent / 1000 + 'k', color: GENDER_COLOR[p.gender] }))} onPinPress={id => router.push(`/pg/${id}`)} />
      <T v="smBold">{list.length ? `${list.length} PG${list.length === 1 ? '' : 's'} within ${RADIUS_KM} km of ${near.name} · nearest first` : 'No PGs match'}</T>
      {list.length === 0 && <Card><T v="sm">Nothing matches “{q.trim()}”{girls ? ' among girls’ PGs' : ''}. Try a sector number or a PG name.</T><Btn kind="secondary" small label="Clear search" onPress={() => { setQ(''); setGirls(false); }} /></Card>}
      {list.map(({ p, km }) => (
        <Pressable key={p.id} onPress={() => router.push(`/pg/${p.id}`)} style={({ pressed }) => ({ backgroundColor: C.surface, borderRadius: R.lg, borderWidth: 1, borderColor: C.line, padding: 14, gap: 4, opacity: pressed ? 0.85 : 1 })}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <T v="price">{rupees(p.rent)}<T v="sm"> /bed</T></T>
            {p.hot ? <Badge label="High demand" tone="warn" /> : <Badge label={`${p.free} free`} tone="ok" />}
          </View>
          <T v="bodyBold">{p.name}</T>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Dot color={GENDER_COLOR[p.gender]} /><T v="sm">{p.gender} · {p.meals} · {p.area}</T></View>
          <T v="smBold" style={{ color: C.accent }}>{km} km from {near.name}</T>
        </Pressable>
      ))}
    </Screen>
  );
}
