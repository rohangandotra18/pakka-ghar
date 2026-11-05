import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Loading } from '@/components/Loading';
import { Btn, Card, Screen, T } from '@/components/ui';
import { api, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { C } from '@/lib/theme';

export default function Beds() {
  const q = useQuery(() => ok(api.GET('/api/owner/beds')));
  const [all, setAll] = useState(false);
  const { act, busy } = useAction();
  const b = q.data;
  if (!b) return <Screen><AppBar /><Loading error={q.error} retry={q.reload} /></Screen>;
  /* rooms with something to act on come first; full rooms fold away */
  const shown = b.rooms.filter(r => all || !r.full);
  return (
    <Screen>
      <AppBar />
      <T v="h2">Bed board</T>
      <T v="sm">{b.free} bed{b.free === 1 ? '' : 's'} free.{b.rooms.some(r => r.beds.some(x => x.tag === 'offers')) ? ' Demand is high, so offers are open on the bed with the most interest.' : ''}</T>
      {shown.map(room => (
        <Card key={room.number}>
          <T v="smBold">Room {room.number}</T>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {room.beds.map(x => {
              const free = !x.who;
              const bg = free ? C.okBg : x.tag === 'leaving' ? C.warnBg : x.tag === 'new' ? C.surface2 : C.accentSoft;
              const cell = (
                <View style={{ flex: 1, minHeight: 52, borderRadius: 10, padding: 8, backgroundColor: bg, borderWidth: free ? 1 : 0, borderColor: C.ok, borderStyle: 'dashed' }}>
                  <T v="smBold" style={{ fontSize: 12, color: free ? C.ok : C.ink }}>{x.who ?? `Bed ${x.label}`}</T>
                  <T v="sm" style={{ fontSize: 11 }}>{x.note || ' '}</T>
                </View>
              );
              if (x.tag === 'offers') return <Pressable key={x.bed_id} style={{ flex: 1 }} accessibilityRole="button" accessibilityLabel={`Room ${room.number} bed ${x.label}: see offers`} onPress={() => router.push('/offers')}>{cell}</Pressable>;
              /* a free bed in demand can take sealed offers instead of the first booking */
              if (x.tag === 'free') return <Pressable key={x.bed_id} style={{ flex: 1 }} disabled={busy} accessibilityRole="button" accessibilityLabel={`Room ${room.number} bed ${x.label}: take offers`}
                onPress={() => act(() => ok(api.POST('/api/owner/beds/{bed_id}/offers', { params: { path: { bed_id: x.bed_id } }, body: { open: true } })), `Taking offers on Room ${room.number}, bed ${x.label} until Friday 6 pm.`)}>{cell}</Pressable>;
              return <View key={x.bed_id} style={{ flex: 1 }}>{cell}</View>;
            })}
          </View>
        </Card>
      ))}
      {b.rooms.length === 0 && <T v="sm">No rooms yet. Add them in setup.</T>}
      {b.free > 0 && <T v="sm">Tap a free bed to take sealed offers on it until Friday 6 pm.</T>}
      {b.full_rooms > 0 && <Btn kind="ghost" label={all ? 'Hide full rooms' : `${b.full_rooms} more room${b.full_rooms === 1 ? ' is' : 's are'} full · show`} onPress={() => setAll(!all)} />}
    </Screen>
  );
}
