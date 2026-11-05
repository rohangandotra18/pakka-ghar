import { useState } from 'react';
import { View } from 'react-native';
import { Loading, Back, Badge, Btn, Card, Chip, Chips, Field, Note, Screen, Stars, T } from '@/design';
import { api, inr, ok, type Schemas, useAction, useQuery } from '@/core/api';

type App = Schemas['OwnerApplicationOut'];
const closes = (iso?: string | null) => (iso ? new Date(iso).toLocaleString('en-IN', { weekday: 'long', hour: 'numeric', hour12: true }).toLowerCase() : 'Friday 6 pm');
const date = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

/* The owner's inbox: requests to stay (alone or with roommates) and sealed bids on rooms up for bids, best bids
   first. Accepting holds a bed for each person for 24 hours while they pay their deposits. */
export default function Applications() {
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/owner/applications')));
  const [rooms, setRooms] = useState<Record<string, string>>({});
  const [declining, setDeclining] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const d = q.data;
  if (!d) return <Screen><Back /><Loading error={q.error} retry={q.reload} /></Screen>;
  const card = (a: App) => {
    const pick = rooms[a.id] ?? a.fits[0];
    return (
      <Card key={a.id}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <T v="bodyBold" style={{ flex: 1 }}>{a.members.map(m => m.name).join(' + ')}</T>
          <T v="price">{inr(a.rent_paise || null)}</T>
        </View>
        <T v="sm">{a.amount_paise ? `Bid on Room ${a.room}` : a.room ? `Room ${a.room}` : `Any ${a.room_kind || ''} room`.replace('  ', ' ')} · {a.size} bed{a.size > 1 ? 's' : ''} · {a.months} months from {date(a.move_in_on)}</T>
        {a.members.map(m => (
          <View key={m.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <T v="sm" style={{ color: '#111714' }}>{m.name}{m.works_at ? ` · ${m.works_at}` : ''}</T>
            <Badge label={m.verified ? 'ID verified' : 'ID pending'} tone={m.verified ? 'ok' : 'warn'} />
            {m.past_stays && m.score != null ? <><Stars value={m.score} /><T v="sm">{m.score} from {m.past_stays} past stay{m.past_stays > 1 ? 's' : ''}</T></> : <T v="sm">No rental history yet</T>}
          </View>
        ))}
        {a.message ? <T v="sm">“{a.message}”</T> : null}
        {!a.room && a.fits.length > 1 && <>
          <T v="sm">Put them in</T>
          <Chips>{a.fits.map(r => <Chip key={r} label={`Room ${r}`} on={pick === r} onPress={() => setRooms(x => ({ ...x, [a.id]: r }))} />)}</Chips>
        </>}
        {!a.room && a.fits.length === 0 && <Note tone="warn">No room has {a.size} free beds together for {date(a.move_in_on)} right now.</Note>}
        {declining === a.id ? <>
          <Field label="Reason (they’ll see it)" value={reason} onChangeText={setReason} placeholder="Optional, e.g. full for December" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small kind="secondary" style={{ flex: 1 }} label="Keep it" onPress={() => setDeclining(null)} />
            <Btn small style={{ flex: 1 }} label="Decline" disabled={busy} onPress={() => act(async () => { await ok(api.POST('/api/owner/applications/{app_id}/decline', { params: { path: { app_id: a.id } }, body: { reason } })); setDeclining(null); setReason(''); }, 'Declined. They’ve been told.')} />
          </View>
        </> : (
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small style={{ flex: 1 }} label={a.members.every(m => m.verified) ? 'Accept' : 'ID pending'} disabled={busy || !a.members.every(m => m.verified) || (!a.room && !pick)}
              onPress={() => act(() => ok(api.POST('/api/owner/applications/{app_id}/accept', { params: { path: { app_id: a.id } }, body: { room: a.room ? '' : pick ?? '' } })),
                `Accepted. ${a.size > 1 ? 'Each of them has' : 'They have'} 24 hours to pay the deposit and sign.`)} />
            <Btn small kind="secondary" style={{ flex: 1 }} label="Decline" onPress={() => setDeclining(a.id)} />
          </View>
        )}
      </Card>
    );
  };
  const bids = d.applications.filter(a => a.amount_paise != null);
  const stays = d.applications.filter(a => a.amount_paise == null);
  return (
    <Screen>
      <Back />
      <T v="h2">Applications</T>
      {d.bidding.map(r => (
        <Card key={r.number} soft>
          <T v="bodyBold">Room {r.number} is up for bids</T>
          <T v="sm">{r.kind} · rent {inr(r.rent_paise)} · bids up to {inr(r.cap_paise)} · {r.free} free bed{r.free === 1 ? '' : 's'} · closes {closes(r.closes_at)}</T>
          <Btn small kind="ghost" label="Stop taking bids" disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/rooms/{number}/bidding', { params: { path: { number: r.number } }, body: { open: false } })), 'Bidding closed. Everyone who bid has been told.')} />
        </Card>
      ))}
      {bids.length > 0 && <T v="label">Bids, highest first</T>}
      {bids.map(card)}
      {stays.length > 0 && <T v="label">Requests to stay</T>}
      {stays.map(card)}
      {d.applications.length === 0 && <Card><T v="sm">No applications waiting. They show up here, with each person’s verified ID and rental history, as tenants apply.</T></Card>}
      {d.decided.length > 0 && <T v="label">Recently decided</T>}
      {d.decided.map(a => <T key={a.id} v="sm">{a.members.map(m => m.name).join(' + ')} · {a.status === 'accepted' ? `accepted, Room ${a.room}` : 'declined'}</T>)}
    </Screen>
  );
}
