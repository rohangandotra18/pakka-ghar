import { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { Pressable, View } from 'react-native';
import { Tick } from '@/components/icons';
import { Loading } from '@/components/Loading';
import { Back, Btn, Chip, Chips, Hero, List, Note, Row, Screen, T } from '@/components/ui';
import { api, inr, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { C, R } from '@/lib/theme';

const STEP = 10000; // ₹100 in paise

/* A sealed offer on a scarce bed: capped at 15% over the listed rent, deposit unchanged, nothing charged unless accepted. */
export default function MakeOffer() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { act, busy } = useAction();
  const listing = useQuery(() => ok(api.GET('/api/listings/{slug}', { params: { path: { slug: id } } })), [id]);
  const mine = useQuery(() => ok(api.GET('/api/offers/mine')), [id]);
  const o = (mine.data ?? []).find(x => x.listing === id && (x.status === 'placed' || x.status === 'accepted'));
  const p = listing.data;
  const listed = p?.free_bed?.offers_open ? p.free_bed.rent_paise : o?.listed_paise ?? p?.rent_paise ?? 0;
  const cap = p?.offers?.cap_paise ?? o?.cap_paise ?? Math.round((listed * 1.15) / 5000) * 5000;
  const [draft, setAmount] = useState<number | null>(null);
  const [chosenMonths, setMonths] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const amount = draft ?? o?.amount_paise ?? Math.min(cap, Math.round((listed * 1.1) / 5000) * 5000);
  const months = chosenMonths ?? o?.months ?? 11;
  if (!p || !mine.data) return <Screen><Back /><Loading error={listing.error ?? mine.error} retry={listing.reload} /></Screen>;
  const step = (d: number) => setAmount(Math.min(cap, Math.max(listed, amount + d)));

  if (o?.status === 'accepted') return (
    <Screen>
      <Back />
      <Hero icon={<Tick />} title="Offer accepted" body={`${p.name} accepted ${inr(o.amount_paise)} a month for ${o.months} months. Pay the deposit within 24 hours to hold the bed.`} />
      <Btn label="Pay deposit and sign" onPress={() => router.push(`/book/${p.id}`)} />
    </Screen>
  );
  if (o && !editing) {
    const closes = o.closes_at ? new Date(o.closes_at).toLocaleString('en-IN', { weekday: 'long', hour: 'numeric', hour12: true }).toLowerCase() : 'Friday 6 pm';
    return (
      <Screen>
        <Back />
        <T v="h2">Your offer</T>
        <List>
          <Row left="Rent offered" right={`${inr(o.amount_paise)}/month`} />
          <Row left="Stay" right={`${o.months} months`} />
          <Row left="Move-in" right={new Date(o.move_in_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' })} />
          <Row left="Offers so far" right={`${o.count} · ${inr(o.min_paise)}–${inr(o.max_paise)}`} />
          <Row left="Your standing" right={o.rank === 1 ? 'Highest rent so far' : `${o.rank} of ${o.count} on rent`} last />
        </List>
        <T v="sm">Owners weigh rent, stay length and your verified rental history. You’ll hear by {closes}. Nothing is charged unless your offer is accepted.</T>
        <Btn kind="secondary" label="Change offer" onPress={() => setEditing(true)} />
        <Btn kind="ghost" label="Withdraw offer" disabled={busy} onPress={() => act(async () => { await ok(api.DELETE('/api/offers/{offer_id}', { params: { path: { offer_id: o.id } } })); setAmount(null); setMonths(null); }, 'Offer withdrawn.')} />
      </Screen>
    );
  }
  const pct = (amount - listed) / (cap - listed || 1);
  return (
    <Screen>
      <Back />
      <T v="h2">{o ? 'Change your offer' : 'Make an offer'}</T>
      <T v="sm">{p.name} · {p.free_bed?.kind.toLowerCase() ?? 'shared room'} · listed at {inr(listed)}</T>
      <View style={{ alignItems: 'center', gap: 10, paddingVertical: 6 }}>
        <T v="h1" style={{ fontSize: 36, lineHeight: 42 }}>{inr(amount)}<T v="sm"> /month</T></T>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, alignSelf: 'stretch' }}>
          <StepBtn label="−" onPress={() => step(-STEP)} />
          <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: C.line }}><View style={{ width: `${Math.round(pct * 100)}%`, height: 6, borderRadius: 3, backgroundColor: C.accent }} /></View>
          <StepBtn label="+" onPress={() => step(STEP)} />
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignSelf: 'stretch' }}><T v="sm">Listed {inr(listed)}</T><T v="sm">Cap {inr(cap)} (15%)</T></View>
      </View>
      <T v="label">Stay length</T>
      <Chips>{[6, 9, 11].map(m => <Chip key={m} label={`${m} months`} on={months === m} onPress={() => setMonths(m)} />)}</Chips>
      <Note tone="soft">Longer stays and a good rental history count as much as rent. Offers can’t go more than 15% over the listed rent, and the deposit stays at one month.</Note>
      <Btn label={o ? 'Update offer' : 'Place offer'} disabled={busy} onPress={() => act(async () => { await ok(api.POST('/api/offers', { body: { listing: id, amount_paise: amount, months } })); setEditing(false); }, "Offer placed. Nothing is charged unless it's accepted.")} />
    </Screen>
  );
}
function StepBtn({ label, onPress }: { label: string; onPress: () => void }) {
  return <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label === '+' ? 'Raise offer by ₹100' : 'Lower offer by ₹100'} style={{ width: 44, height: 44, borderRadius: R.md, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center' }}><T v="h3">{label}</T></Pressable>;
}
