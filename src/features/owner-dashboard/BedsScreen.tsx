import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { AppBar } from '@/shared';
import { Loading, Btn, Card, Chip, Otp, Screen, T, C } from '@/design';
import { api, ApiError, ok, useAction, useQuery } from '@/core/api';

export default function Beds() {
  const q = useQuery(() => ok(api.GET('/api/owner/beds')));
  const [all, setAll] = useState(false);
  const { act, busy } = useAction();
  /* switching instant booking on takes a code: it stands as your signature on each instant acceptance */
  const [consent, setConsent] = useState<{ room: string; id: string; code: string; last4: string } | null>(null);
  const b = q.data;
  const startInstant = (number: string) => act(async () => {
    try {
      const r = await ok(api.POST('/api/owner/rooms/{number}/instant/start', { params: { path: { number } } }));
      setConsent({ room: number, id: r.challenge_id, code: r.dev_code ?? '', last4: r.phone_last4 });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'payout_first') { router.push('/onboarding/owner?step=payouts'); return; }
      throw e;
    }
  });
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
          {!room.bidding && <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <T v="sm" style={{ flex: 1 }}>{room.instant ? 'Instant booking on: verified tenants book without waiting for you.' : 'Instant booking off: you accept each request.'}</T>
            <Chip label={room.instant ? 'Turn off' : 'Turn on'} on={room.instant} onPress={() => (room.instant
              ? act(() => ok(api.POST('/api/owner/rooms/{number}/instant', { params: { path: { number: room.number } }, body: { on: false, challenge_id: '', code: '' } })), `Instant booking off for Room ${room.number}.`)
              : startInstant(room.number))} />
          </View>}
          {consent?.room === room.number && <>
            <T v="sm">With instant booking, a verified tenant’s request for Room {room.number} is accepted and signed for you at once; they then sign and pay. Confirm with the code sent to your phone ending {consent.last4}.</T>
            <Otp code={consent.code} onChange={code => setConsent(x => x && { ...x, code })} />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <Btn small kind="secondary" style={{ flex: 1 }} label="Cancel" onPress={() => setConsent(null)} />
              <Btn small style={{ flex: 1 }} label="Turn on instant booking" disabled={busy} onPress={() => act(async () => {
                await ok(api.POST('/api/owner/rooms/{number}/instant', { params: { path: { number: room.number } }, body: { on: true, challenge_id: consent.id, code: consent.code } }));
                setConsent(null);
                q.reload();
              }, `Instant booking on for Room ${room.number}.`)} />
            </View>
          </>}
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
      {b.free > 0 && <T v="sm">“Take bids” puts a room up for sealed bids, up to 15% over the rent, until Friday 6 pm. Otherwise tenants request a bed at the listed rent and you choose, or they book at once on rooms with instant booking.</T>
      }<Btn kind="secondary" label="See requests" onPress={() => router.push('/applications')} />
      {b.full_rooms > 0 && <Btn kind="ghost" label={all ? 'Hide full rooms' : `${b.full_rooms} more room${b.full_rooms === 1 ? ' is' : 's are'} full · show`} onPress={() => setAll(!all)} />}
    </Screen>
  );
}
