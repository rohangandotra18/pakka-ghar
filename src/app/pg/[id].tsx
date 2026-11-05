import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { MapView } from '@/components/MapView';
import { Loading } from '@/components/Loading';
import { Back, Badge, Btn, Dot, List, Note, Row, Screen, Stars, T } from '@/components/ui';
import { api, inr, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { useStore } from '@/lib/store';
import { GENDER_COLOR } from '@/lib/theme';

const closes = (iso?: string | null) => (iso ? new Date(iso).toLocaleString('en-IN', { weekday: 'long', hour: 'numeric', hour12: true }).replace(/ (am|pm)/i, ' $1').toLowerCase() : 'Friday 6 pm');

export default function PGDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { tenantReady } = useStore();
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/listings/{slug}', { params: { path: { slug: id } } })), [id]);
  const mine = useQuery(() => (tenantReady ? ok(api.GET('/api/offers/mine')) : Promise.resolve([])), [tenantReady]);
  /* browsing is open; acting needs a verified account. Sign-up then carries straight on to `next`,
     or returns here when there's no next screen (a visit request). */
  const needSignup = (why: string, next?: string) => { if (tenantReady) return false; router.push({ pathname: '/onboarding/tenant', params: next ? { why, next, listing: id } : { why, listing: id } }); return true; };
  const p = q.data;
  if (!p) return <Screen><Back /><Loading error={q.error} retry={q.reload} /></Screen>;
  const myOffer = (mine.data ?? []).find(o => o.listing === p.id && (o.status === 'placed' || o.status === 'accepted'));
  const bed = p.free_bed;
  return (
    <Screen>
      <Back />
      <MapView height={200} center={{ lat: p.lat, lng: p.lng }} zoom={15} pins={[{ id: p.id, lat: p.lat, lng: p.lng, label: '₹' + Math.round(p.rent_paise / 100000 * 10) / 10 + 'k', color: GENDER_COLOR[p.gender] }]} />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><T v="h2" style={{ flex: 1 }}>{p.name}</T>{p.verified_owner && <Badge label="Verified owner" tone="ok" />}</View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}><Dot color={GENDER_COLOR[p.gender]} /><T v="sm">{p.gender} · {p.area}</T>{p.rating != null && <><Stars value={p.rating} /><T v="sm">{p.rating} ({p.stays} stays)</T></>}</View>
      {p.hot && <Note><T v="sm" style={{ color: '#111714' }}><T v="smBold">High demand. </T>{p.free} bed{p.free === 1 ? '' : 's'} free{p.watching ? `, ${p.watching} people interested` : ''}. Offers on Room {bed?.room} are open until {closes(p.offers?.closes_at)}; the owner picks one.</T></Note>}
      <List>
        <Row left={bed?.kind ?? 'Rent per bed'} right={`${inr(p.rent_paise)} · ${p.free} free`} />
        <Row left="Deposit" right={`${p.deposit_months} month, in escrow`} />
        <Row left="Electricity" right={`By meter, ₹${(p.tariff_paise / 100).toFixed(2)}/unit`} />
        <Row left="Meals" right={p.meals} />
        <Row left="Payment" right="In the app only" />
        <Row left="Fees" right="None, Pakka Ghar is free" last />
      </List>
      {!bed && <Note tone="soft">Every bed is taken for {new Date(p.move_in_on).toLocaleString('en-IN', { month: 'long' })}. Book a visit to be first when one frees up.</Note>}
      {bed && (p.hot
        ? <Btn label={myOffer ? (myOffer.status === 'accepted' ? 'Your offer was accepted' : 'See your offer') : 'Make an offer'} onPress={() => { if (needSignup('offer', `/offer/${p.id}`)) return; router.push(`/offer/${p.id}`); }} />
        : <Btn label="Book this bed" onPress={() => { if (needSignup('book', `/book/${p.id}`)) return; router.push(`/book/${p.id}`); }} />)}
      <Btn kind="secondary" label="Book a visit" disabled={busy} onPress={() => { if (needSignup('visit')) return; act(() => ok(api.POST('/api/visits', { body: { listing: p.id } })), 'Visit requested for Saturday 11 am. The owner confirms in the app.'); }} />
      <T v="sm">The pin is the building the owner marked when listing. Pakka Ghar is free: no brokerage, no fees.</T>
    </Screen>
  );
}
