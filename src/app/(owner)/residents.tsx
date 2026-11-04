import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Badge, List, Row, Screen, Stars, T } from '@/components/ui';
import { PAST_RESIDENTS, RESIDENTS } from '@/lib/data';
import { useStore } from '@/lib/store';
import { C } from '@/lib/theme';

/* The owner's resident database: everyone current and past stays on record. */
export default function Residents() {
  const { s } = useStore();
  const [tab, setTab] = useState<'current' | 'past'>('current');
  const seg = (k: 'current' | 'past', label: string) => (
    <Pressable onPress={() => setTab(k)} accessibilityRole="tab" accessibilityState={{ selected: tab === k }} style={{ flex: 1, paddingVertical: 8, borderRadius: 9, alignItems: 'center', backgroundColor: tab === k ? C.surface : 'transparent', borderWidth: tab === k ? 1 : 0, borderColor: C.line }}>
      <T v="smBold" style={{ color: tab === k ? C.ink : C.muted }}>{label}</T>
    </Pressable>
  );
  return (
    <Screen>
      <AppBar />
      <T v="h2">Residents</T>
      <View style={{ flexDirection: 'row', backgroundColor: C.surface2, borderRadius: 11, padding: 3 }}>{seg('current', 'Current (21)')}{seg('past', 'Past (37)')}</View>
      {tab === 'current' ? (
        <List>
          {RESIDENTS.map((r, i) => {
            const pv = s.police[r.name] ?? r.police;
            return (
              <Pressable key={r.name} onPress={() => router.push(`/resident/${r.name}`)}>
                <Row last={i === RESIDENTS.length - 1} left={<View><T v="bodyBold">{r.name}</T><T v="sm">Room {r.room} · since {r.since}</T></View>} right={<Badge label={pv} tone={pv === 'Verified' ? 'ok' : pv === 'Submitted' ? 'warn' : 'crit'} />} />
              </Pressable>
            );
          })}
        </List>
      ) : (
        <>
          <List>
            {PAST_RESIDENTS.map((r, i) => <Row key={r.name} last={i === PAST_RESIDENTS.length - 1} left={<View><T v="bodyBold">{r.name}</T><T v="sm">Room {r.room} · {r.from} – {r.to}</T><T v="sm" style={{ color: C.ink }}>{r.deposit}</T></View>} right={<Stars value={r.rating} />} />)}
          </List>
          <T v="sm">Every resident stays on record: ID check, agreement, payments, deposit outcome and ratings.</T>
        </>
      )}
    </Screen>
  );
}
