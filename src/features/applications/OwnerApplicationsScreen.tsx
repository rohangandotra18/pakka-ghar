import { useState } from 'react';
import { View } from 'react-native';
import { AppBar } from '@/shared';
import { Loading, Badge, Btn, Card, Chip, Chips, Field, Note, Otp, Screen, Stars, T, C, dayHour } from '@/design';
import { api, ApiError, inr, ok, type Schemas, useAction, useQuery } from '@/core/api';

type App = Schemas['OwnerApplicationOut'];
const closes = (iso?: string | null) => (iso ? dayHour(iso) : 'Friday 6 pm');
const date = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

/* The owner's inbox: requests to stay (alone or with roommates) and sealed bids on rooms up for bids, best bids
   first. Accepting is signing: one code signs the owner's side of each person's agreement, and their beds are held
   24 hours for them to sign and pay. The bank account rent goes to is asked for here, at the first accept. */
export default function Applications() {
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/owner/applications')));
  const [rooms, setRooms] = useState<Record<string, string>>({});
  const [declining, setDeclining] = useState<string | null>(null);
  const [stopping, setStopping] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [signing, setSigning] = useState<{ app: string; id: string; code: string; last4: string } | null>(null);
  const [bankFor, setBankFor] = useState<string | null>(null);
  const [bank, setBank] = useState({ bank: '', account: '', ifsc: '' });
  const d = q.data;
  const startAccept = (appId: string) => act(async () => {
    try {
      const r = await ok(api.POST('/api/owner/applications/{app_id}/accept/start', { params: { path: { app_id: appId } } }));
      setBankFor(null);
      setSigning({ app: appId, id: r.challenge_id, code: r.dev_code ?? '', last4: r.phone_last4 });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'payout_first') { setBankFor(appId); return; }
      throw e;
    }
  });
  const saveBank = (appId: string) => act(async () => {
    await ok(api.POST('/api/owner/payout', { body: { bank_name: bank.bank, account_number: bank.account, ifsc: bank.ifsc } }));
    const r = await ok(api.POST('/api/owner/applications/{app_id}/accept/start', { params: { path: { app_id: appId } } }));
    setBankFor(null);
    setSigning({ app: appId, id: r.challenge_id, code: r.dev_code ?? '', last4: r.phone_last4 });
  }, 'Bank account saved.');
  if (!d) return <Screen><AppBar /><Loading error={q.error} retry={q.reload} /></Screen>;
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
            <T v="sm" style={{ color: C.ink }}>{m.name}{m.works_at ? ` · ${m.works_at}` : ''}</T>
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
        {bankFor === a.id ? <>
          <T v="bodyBold">Where should rent be paid?</T>
          <T v="sm">Needed once, before your first resident. We check it with a ₹1 test deposit.</T>
          <Field label="Bank" value={bank.bank} onChangeText={t => setBank(x => ({ ...x, bank: t }))} placeholder="e.g. HDFC Bank" />
          <Field label="Account number" value={bank.account} onChangeText={t => setBank(x => ({ ...x, account: t }))} keyboard="number-pad" placeholder="As on your passbook or cheque" />
          <Field label="IFSC" value={bank.ifsc} onChangeText={t => setBank(x => ({ ...x, ifsc: t }))} placeholder="Like SBIN0001234" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small kind="secondary" style={{ flex: 1 }} label="Not now" onPress={() => setBankFor(null)} />
            <Btn small style={{ flex: 1 }} label="Save and continue" disabled={busy || !bank.bank.trim() || !bank.account.trim() || bank.ifsc.trim().length !== 11} onPress={() => saveBank(a.id)} />
          </View>
        </> : signing?.app === a.id ? <>
          <T v="sm">Accepting signs your side of {a.size > 1 ? 'each of their agreements' : 'their agreement'}. Code sent to your phone ending {signing.last4}.</T>
          <Otp code={signing.code} onChange={code => setSigning(x => x && { ...x, code })} />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small kind="secondary" style={{ flex: 1 }} label="Back" onPress={() => setSigning(null)} />
            <Btn small style={{ flex: 1 }} label="Accept and sign" disabled={busy} onPress={() => act(async () => {
              await ok(api.POST('/api/owner/applications/{app_id}/accept', { params: { path: { app_id: a.id } }, body: { room: a.room ? '' : pick ?? '', challenge_id: signing.id, code: signing.code } }));
              setSigning(null);
              q.reload();
            }, `Accepted and signed. ${a.size > 1 ? 'Each of them has' : 'They have'} 24 hours to sign and pay the deposit.`)} />
          </View>
        </> : declining === a.id ? <>
          <Field label="Reason (they’ll see it)" value={reason} onChangeText={setReason} placeholder="Optional, e.g. full for December" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small kind="secondary" style={{ flex: 1 }} label="Keep it" onPress={() => setDeclining(null)} />
            <Btn small style={{ flex: 1 }} label="Decline" disabled={busy} onPress={() => act(async () => { await ok(api.POST('/api/owner/applications/{app_id}/decline', { params: { path: { app_id: a.id } }, body: { reason } })); setDeclining(null); setReason(''); }, 'Declined. They’ve been told.')} />
          </View>
        </> : (
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small style={{ flex: 1 }} label={a.members.every(m => m.verified) ? 'Accept' : 'ID pending'} disabled={busy || !a.members.every(m => m.verified) || (!a.room && !pick)}
              onPress={() => startAccept(a.id)} />
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
      <AppBar />
      <T v="h2">Requests</T>
      {d.bidding.map(r => (
        <Card key={r.number} soft>
          {/* after the deadline no new bids or requests come in for the room until the owner picks one */}
          {r.closes_at && new Date(r.closes_at) < new Date() ? <>
            <T v="bodyBold">Bidding on Room {r.number} has ended</T>
            <T v="sm">Pick a bid below to fill the {r.free === 1 ? 'bed' : `${r.free} beds`}. Until you do, the room takes no new requests.</T>
          </> : <>
            <T v="bodyBold">Room {r.number} is up for bids</T>
            <T v="sm">{r.kind} · rent {inr(r.rent_paise)} · bids up to {inr(r.cap_paise)} · {r.free} free bed{r.free === 1 ? '' : 's'} · closes {closes(r.closes_at)}</T>
          </>}
          {stopping === r.number ? <>
            <T v="sm" style={{ color: C.ink }}>Every bid on Room {r.number} will be declined and each bidder told. The room goes back to requests at the listed rent.</T>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <Btn small kind="secondary" style={{ flex: 1 }} label="Keep the bids" onPress={() => setStopping(null)} />
              <Btn small style={{ flex: 1 }} label="Decline them all" disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/rooms/{number}/bidding', { params: { path: { number: r.number } }, body: { open: false } })), 'Bidding closed. Everyone who bid has been told.').then(() => setStopping(null))} />
            </View>
          </> : <Btn small kind="ghost" label="Stop taking bids" onPress={() => setStopping(r.number)} />}
        </Card>
      ))}
      {bids.length > 0 && <T v="label">Bids, highest first</T>}
      {bids.map(card)}
      {stays.length > 0 && <T v="label">Requests to stay</T>}
      {stays.map(card)}
      {d.applications.length === 0 && <Card><T v="sm">No requests waiting. They show up here, with each person’s verified ID and rental history, as tenants send them.</T></Card>}
      {d.decided.length > 0 && <T v="label">Recently decided</T>}
      {d.decided.map(a => <T key={a.id} v="sm">{a.members.map(m => m.name).join(' + ')} · {a.status === 'accepted' ? `accepted, Room ${a.room}` : 'declined'}</T>)}
    </Screen>
  );
}
