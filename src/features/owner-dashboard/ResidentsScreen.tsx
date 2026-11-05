import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { AppBar } from '@/shared';
import { Loading, Badge, List, Row, Screen, Stars, T, C } from '@/design';
import { api, ok, useQuery } from '@/core/api';

/* The owner's resident database: everyone current and past stays on record. */
export default function Residents() {
  const [tab, setTab] = useState<'current' | 'past'>('current');
  const q = useQuery(() => ok(api.GET('/api/owner/residents', { params: { query: { tab } } })), [tab]);
  const r = q.data;
  const seg = (k: 'current' | 'past', label: string) => (
    <Pressable onPress={() => setTab(k)} accessibilityRole="tab" accessibilityState={{ selected: tab === k }} style={{ flex: 1, paddingVertical: 8, borderRadius: 9, alignItems: 'center', backgroundColor: tab === k ? C.surface : 'transparent', borderWidth: tab === k ? 1 : 0, borderColor: C.line }}>
      <T v="smBold" style={{ color: tab === k ? C.ink : C.muted }}>{label}</T>
    </Pressable>
  );
  return (
    <Screen>
      <AppBar />
      <T v="h2">Residents</T>
      <View style={{ flexDirection: 'row', backgroundColor: C.surface2, borderRadius: 11, padding: 3 }}>{seg('current', `Current${r ? ` (${r.current})` : ''}`)}{seg('past', `Past${r ? ` (${r.past})` : ''}`)}</View>
      {!r ? <Loading error={q.error} retry={q.reload} /> : r.items.length === 0 ? <T v="sm">No one yet.</T> : (
        <List>
          {r.items.map((x, i) => (
            <Pressable key={x.booking_id} onPress={() => router.push(`/resident/${x.booking_id}`)}>
              {tab === 'current'
                ? <Row last={i === r.items.length - 1} left={<View><T v="bodyBold">{x.name}</T><T v="sm">Room {x.room} · since {x.since}</T></View>} right={<Badge label={x.police} tone={x.police === 'Verified' ? 'ok' : x.police === 'Submitted' ? 'warn' : 'crit'} />} />
                : <Row last={i === r.items.length - 1} left={<View><T v="bodyBold">{x.name}</T><T v="sm">Room {x.room} · {x.since} – {x.to}</T><T v="sm" style={{ color: C.ink }}>{x.deposit}</T></View>} right={x.rating != null ? <Stars value={x.rating} /> : <T v="sm">Not rated</T>} />}
            </Pressable>
          ))}
        </List>
      )}
      {r && <T v="sm">{tab === 'current' ? 'Every resident stays on record: ID check, agreement, payments, deposit outcome and ratings.' : 'Past residents stay on record with their deposit outcome and rating.'}</T>}
    </Screen>
  );
}
