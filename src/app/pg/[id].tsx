import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { MapView } from '@/components/MapView';
import { Back, Badge, Btn, Dot, List, Note, Row, Screen, Stars, T } from '@/components/ui';
import { TARIFF } from '@/lib/data';
import { pgById, pinOf, useStore } from '@/lib/store';
import { GENDER_COLOR, rupees } from '@/lib/theme';

export default function PGDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const p = pgById(id);
  const { s, set, toast } = useStore();
  const pin = pinOf(p, s.pins);
  /* browsing is open; acting needs a verified account, then returns here */
  const needSignup = (why: string, next: string) => { if (s.tenantReady) return false; router.push({ pathname: '/onboarding/tenant', params: { why, next } }); return true; };
  return (
    <Screen>
      <Back />
      <MapView height={200} center={pin} zoom={15} pins={[{ id: p.id, ...pin, label: '₹' + p.rent / 1000 + 'k', color: GENDER_COLOR[p.gender] }]} />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><T v="h2" style={{ flex: 1 }}>{p.name}</T><Badge label="Verified owner" tone="ok" /></View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}><Dot color={GENDER_COLOR[p.gender]} /><T v="sm">{p.gender} · {p.area}</T><Stars value={p.rating} /><T v="sm">{p.rating} ({p.stays} stays)</T></View>
      {p.hot && <Note><T v="sm" style={{ color: '#111714' }}><T v="smBold">High demand. </T>{p.free} bed{p.free === 1 ? '' : 's'} free, {p.watching} people interested. Offers are open until Friday 6 pm; the owner picks one.</T></Note>}
      <List>
        <Row left="Double sharing" right={`${rupees(p.rent)} · ${p.free} free`} />
        <Row left="Deposit" right="1 month, in escrow" />
        <Row left="Electricity" right={`By meter, ₹${TARIFF}/unit`} />
        <Row left="Meals" right={p.meals} />
        <Row left="Payment" right="In the app only" />
        <Row left="Fees" right="None, Pakka Ghar is free" last />
      </List>
      {p.hot
        ? <Btn label={s.offer?.pgId === p.id && s.offer.placed ? 'See your offer' : 'Make an offer'} onPress={() => { if (needSignup('offer', `/pg/${p.id}`)) return; if (s.offer?.pgId !== p.id) set({ offer: { pgId: p.id, amount: Math.round((p.rent * 1.1) / 50) * 50, months: 11, placed: false, accepted: false } }); router.push(`/offer/${p.id}`); }} />
        : <Btn label="Book this bed" onPress={() => { if (needSignup('book', `/pg/${p.id}`)) return; set({ booking: { paid: false, signed: false, stamped: false }, offer: null }); router.push(`/book/${p.id}`); }} />}
      <Btn kind="secondary" label="Book a visit" onPress={() => { if (needSignup('visit', `/pg/${p.id}`)) return; toast('Visit requested for Saturday 11 am. The owner confirms in the app.'); }} />
      <T v="sm">The pin is the building the owner marked when listing. Pakka Ghar is free: no brokerage, no fees.</T>
    </Screen>
  );
}
