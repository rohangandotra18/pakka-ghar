import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { AppBar } from '@/shared';
import { Loading, Btn, Card, Chip, Screen, T, C } from '@/design';
import { api, ok, useAction, useQuery } from '@/core/api';

export default function Beds() {
  const q = useQuery(() => ok(api.GET('/api/owner/beds')));
  const [all, setAll] = useState(false);
  const { act } = useAction();
  const b = q.data;
  if (!b) return <Screen><AppBar /><Loading error={q.error} retry={q.reload} /></Screen>;
  /* rooms with something to act on come first; full rooms fold away */
  const shown = b.rooms.filter(r => all || !r.full);
  return (
    <Screen>
      <AppBar />
      <T v="h2">Bed board</T>
      <T v="sm">{b.free} bed{b.free === 1 ? '' : 's'} free.{b.rooms.some(r => r.bidding) ? ' Rooms up for bids take sealed bids up to 15% over the rent; you pick.' : ''}</T>
      {shown.map(room => (
        <Card key={room.number}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <T v="smBold">Room {room.number}{room.bidding ? ` · up for bids${room.bids ? `, ${room.bids} so far` : ''}` : ''}</T>
            {/* a room in demand can go up for bids instead of first-come applications */}
            {(room.bidding || room.beds.some(x => x.tag === 'free')) && <Chip label={room.bidding ? 'Stop bids' : 'Take bids'} onPress={() => act(
              () => ok(api.POST('/api/owner/rooms/{number}/bidding', { params: { path: { number: room.number } }, body: { open: !room.bidding } })),
              room.bidding ? `Bidding on Room ${room.number} closed. Bidders have been told.` : `Room ${room.number} is up for bids until Friday 6 pm.`)} />}
          </View>
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
              if (x.tag === 'offers') return <Pressable key={x.bed_id} style={{ flex: 1 }} accessibilityRole="button" accessibilityLabel={`Room ${room.number} bed ${x.label}: see bids`} onPress={() => router.push('/applications')}>{cell}</Pressable>;
              return <View key={x.bed_id} style={{ flex: 1 }}>{cell}</View>;
            })}
          </View>
        </Card>
      ))}
      {b.rooms.length === 0 && <T v="sm">No rooms yet. Add them in setup.</T>}
      {b.free > 0 && <T v="sm">“Take bids” puts a room up for sealed bids, up to 15% over the rent, until Friday 6 pm. Otherwise tenants apply at the listed rent and you choose.</T>
      }<Btn kind="secondary" label="See applications" onPress={() => router.push('/applications')} />
      {b.full_rooms > 0 && <Btn kind="ghost" label={all ? 'Hide full rooms' : `${b.full_rooms} more room${b.full_rooms === 1 ? ' is' : 's are'} full · show`} onPress={() => setAll(!all)} />}
    </Screen>
  );
}
