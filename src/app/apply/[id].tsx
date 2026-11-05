import { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { Pressable, TextInput, View } from 'react-native';
import { Loading } from '@/components/Loading';
import { Back, Btn, Chip, Chips, Field, Note, Screen, T } from '@/components/ui';
import { api, inr, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { C, F, R } from '@/lib/theme';

const STEP = 10000; // ₹100
const KINDS: Record<string, string> = { single: 'Single', double: 'Double', triple: 'Triple' };
const MAX_BY_KIND: Record<string, number> = { single: 1, double: 2, triple: 3 };

/* Apply to stay: a specific room or any room, alone or with up to two roommates. On a room that's up for bids,
   the application carries a sealed bid between the rent and 15% over it. */
export default function Apply() {
  const { id, room: preset } = useLocalSearchParams<{ id: string; room?: string }>();
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/listings/{slug}', { params: { path: { slug: id } } })), [id]);
  const [room, setRoom] = useState<string>(preset ?? '');
  const [kind, setKind] = useState('');
  const [bid, setBid] = useState<number | null>(null);
  const [months, setMonths] = useState(11);
  const [mates, setMates] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const p = q.data;
  if (!p) return <Screen><Back /><Loading error={q.error} retry={q.reload} /></Screen>;
  const r = p.rooms.find(x => x.number === room);
  const bidding = !!r?.bidding;
  const amount = bid ?? (r ? Math.min(r.cap_paise, Math.round((r.rent_paise * 1.05) / 5000) * 5000) : 0);
  /* how many people fit: the room's free beds, or the biggest free block of the chosen kind */
  const pool = r ? [r] : p.rooms.filter(x => !x.bidding && (!kind || x.kind === kind));
  const room_for = Math.max(0, ...pool.map(x => Math.min(x.free, MAX_BY_KIND[x.kind] ?? 1)));
  const people = 1 + mates.length;
  const tooMany = people > room_for;
  const kinds = [...new Set(p.rooms.filter(x => !x.bidding).map(x => x.kind))];
  const submit = () => act(async () => {
    await ok(api.POST('/api/applications', { body: {
      listing: id, room, room_kind: room ? '' : kind, amount_paise: bidding ? amount : null, months, message,
      roommates: mates.map(m => m.trim()).filter(Boolean),
    } }));
    router.replace('/stay');
  }, mates.length ? 'Sent. Your roommates get an invite; it goes to the owner once they join.' : 'Sent to the owner. You’ll hear in the app.');

  return (
    <Screen>
      <Back />
      <T v="h2">{bidding ? `Bid on Room ${room}` : 'Apply to stay'}</T>
      <T v="sm">{p.name} · move in from {new Date(p.move_in_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' })}</T>

      <T v="label">Which room</T>
      <Chips>
        <Chip label="Any room" on={!room} onPress={() => { setRoom(''); setBid(null); }} />
        {p.rooms.map(x => <Chip key={x.number} label={`${x.number}${x.bidding ? ' · bids' : ''}`} on={room === x.number} onPress={() => { setRoom(x.number); setBid(null); }} />)}
      </Chips>
      {!room && kinds.length > 1 && <>
        <T v="label">Room type</T>
        <Chips><Chip label="Any" on={!kind} onPress={() => setKind('')} />{kinds.map(k => <Chip key={k} label={KINDS[k] ?? k} on={kind === k} onPress={() => setKind(k)} />)}</Chips>
      </>}
      {r && <T v="sm">Room {r.number}: {r.kind_label}, {inr(r.rent_paise)} a bed, {r.free} of {r.beds} free.</T>}

      {bidding && r && <>
        <T v="label">Your bid, per bed per month</T>
        <View style={{ alignItems: 'center', gap: 10 }}>
          <T v="h1" style={{ fontSize: 34, lineHeight: 40 }}>{inr(amount)}</T>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, alignSelf: 'stretch' }}>
            <StepBtn label="−" onPress={() => setBid(Math.max(r.rent_paise, amount - STEP))} />
            <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: C.line }}><View style={{ width: `${Math.round(((amount - r.rent_paise) / (r.cap_paise - r.rent_paise || 1)) * 100)}%`, height: 6, borderRadius: 3, backgroundColor: C.accent }} /></View>
            <StepBtn label="+" onPress={() => setBid(Math.min(r.cap_paise, amount + STEP))} />
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignSelf: 'stretch' }}><T v="sm">Rent {inr(r.rent_paise)}</T><T v="sm">Cap {inr(r.cap_paise)} (15%)</T></View>
        </View>
        <Note tone="soft">Bids are sealed: others see only how many there are. The deposit stays at one month of the rent, and nothing is charged unless you’re accepted.</Note>
      </>}

      <T v="label">Stay length</T>
      <Chips>{[6, 9, 11].map(m => <Chip key={m} label={`${m} months`} on={months === m} onPress={() => setMonths(m)} />)}</Chips>

      <T v="label">Moving in with someone?</T>
      <T v="sm">Add a roommate’s mobile number. They get an invite, verify in their own app, and you’re given beds in the same room. Each of you pays your own deposit.</T>
      {mates.map((m, i) => (
        <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
          <View style={{ flex: 1 }}><Field label={`Roommate ${i + 1}`} value={m} onChangeText={t => setMates(xs => xs.map((x, j) => (j === i ? t : x)))} keyboard="phone-pad" placeholder="10-digit mobile number" /></View>
          <Btn small kind="ghost" label="Remove" onPress={() => setMates(xs => xs.filter((_, j) => j !== i))} />
        </View>
      ))}
      {mates.length < 2 && people < Math.max(room_for, 1) && <Btn small kind="secondary" label="+ Add a roommate" onPress={() => setMates(xs => [...xs, ''])} />}
      {tooMany && <Note tone="warn">{room_for ? `${r ? `Room ${r.number}` : 'No room'} has only ${room_for} free bed${room_for > 1 ? 's' : ''} together.` : 'No room has free beds together for your group.'} Pick another room or fewer people.</Note>}

      <T v="label">A note to the owner</T>
      <TextInput allowFontScaling={false} multiline value={message} onChangeText={setMessage} maxLength={500}
        placeholder="Where you study or work, when you'd move in, anything they should know" placeholderTextColor={C.muted}
        style={{ minHeight: 80, borderWidth: 1, borderColor: C.line, borderRadius: 11, backgroundColor: C.surface, padding: 12, fontFamily: F.semi, fontSize: 15, color: C.ink, textAlignVertical: 'top' }} />

      <Btn label={bidding ? `Place bid of ${inr(amount)}` : mates.length ? `Apply for ${people} beds` : 'Send application'}
        disabled={busy || tooMany || mates.some(m => m.replace(/\D/g, '').length < 10)} onPress={submit} />
      <T v="sm">The owner sees your verified ID, your rental history and this note. Pakka Ghar is free.</T>
    </Screen>
  );
}
function StepBtn({ label, onPress }: { label: string; onPress: () => void }) {
  return <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label === '+' ? 'Raise bid by ₹100' : 'Lower bid by ₹100'} style={{ width: 44, height: 44, borderRadius: R.md, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center' }}><T v="h3">{label}</T></Pressable>;
}
