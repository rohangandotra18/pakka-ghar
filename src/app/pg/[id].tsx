import { router, useLocalSearchParams, type Href } from 'expo-router';
import { Image, ScrollView, View } from 'react-native';
import { MapView } from '@/components/MapView';
import { Loading } from '@/components/Loading';
import { Back, Badge, Btn, Chip, Dot, List, Note, Row, Screen, Stars, T } from '@/components/ui';
import { api, inr, ok } from '@/api/client';
import { useQuery } from '@/api/hooks';
import { mediaUrl } from '@/lib/camera';
import { useStore } from '@/lib/store';
import { C, GENDER_COLOR, R } from '@/lib/theme';

const closes = (iso?: string | null) => (iso ? new Date(iso).toLocaleString('en-IN', { weekday: 'long', hour: 'numeric', hour12: true }).toLowerCase() : 'Friday 6 pm');
const day = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

export default function PGDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { tenantReady } = useStore();
  const q = useQuery(() => ok(api.GET('/api/listings/{slug}', { params: { path: { slug: id } } })), [id]);
  const mine = useQuery(() => (tenantReady ? ok(api.GET('/api/applications/mine')) : Promise.resolve([])), [tenantReady]);
  /* browsing is open; acting needs a verified account. Sign-up then carries straight on to `next`. */
  const go = (why: string, next: string) => {
    if (!tenantReady) router.push({ pathname: '/onboarding/tenant', params: { why, next, listing: id } });
    else router.push(next as Href);
  };
  const p = q.data;
  if (!p) return <Screen><Back /><Loading error={q.error} retry={q.reload} /></Screen>;
  const live = (mine.data ?? []).find(a => a.listing === p.id && ['forming', 'pending', 'accepted'].includes(a.status));
  const pinLabel = '₹' + Math.round(p.rent_paise / 100000 * 10) / 10 + 'k';
  const map = <MapView height={190} center={{ lat: p.lat, lng: p.lng }} zoom={15} pins={[{ id: p.id, lat: p.lat, lng: p.lng, label: pinLabel, color: GENDER_COLOR[p.gender] }]} />;
  return (
    <Screen>
      <Back />
      {p.photos.length > 0
        ? <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {p.photos.map(ph => (
              <View key={ph.id} style={{ width: 260, gap: 4 }}>
                <Image source={{ uri: mediaUrl(ph.url) }} style={{ width: 260, height: 180, borderRadius: R.md, backgroundColor: C.surface2 }} accessibilityLabel={ph.caption || `Photo${ph.room ? ` of room ${ph.room}` : ''}`} />
                <T v="sm" style={{ fontSize: 11 }}>{ph.room ? `Room ${ph.room} · ` : ''}Taken on site, {day(ph.taken_at)}</T>
              </View>
            ))}
          </ScrollView>
        : map}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><T v="h2" style={{ flex: 1 }}>{p.name}</T>{p.verified_owner && <Badge label="Verified owner" tone="ok" />}</View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}><Dot color={GENDER_COLOR[p.gender]} /><T v="sm">{p.gender} · {p.area}</T>{p.rating != null && <><Stars value={p.rating} /><T v="sm">{p.rating} ({p.stays} stays)</T></>}</View>
      {p.photos.length > 0 && <T v="sm">Every photo was taken at the building with the Pakka Ghar camera. No stock, edited or AI pictures.</T>}

      <T v="label">Rooms with a free bed</T>
      {p.rooms.length === 0 ? <Note tone="soft">Every bed is taken for now. Schedule a tour to be first when one frees up.</Note> : (
        <List>
          {p.rooms.map((r, i) => (
            <Row key={r.number} last={i === p.rooms.length - 1}
              left={<View style={{ gap: 2 }}>
                <T v="bodyBold">Room {r.number} · {r.kind_label}</T>
                <T v="sm">{inr(r.rent_paise)} a bed · {r.free} of {r.beds} free</T>
                {r.bidding && <T v="sm" style={{ color: C.warn }}>Up for bids until {closes(r.closes_at)}{r.bids ? ` · ${r.bids} bid${r.bids > 1 ? 's' : ''}` : ''}</T>}
              </View>}
              right={!live ? <Chip label={r.bidding ? 'Bid' : 'Apply'} onPress={() => go(r.bidding ? 'offer' : 'book', `/apply/${p.id}?room=${r.number}`)} /> : undefined} />
          ))}
        </List>
      )}
      <List>
        <Row left="Deposit" right={`${p.deposit_months} month, in escrow`} />
        <Row left="Electricity" right={`By meter, ₹${(p.tariff_paise / 100).toFixed(2)}/unit`} />
        <Row left="Meals" right={p.meals} />
        <Row left="Payment" right="In the app only" />
        <Row left="Fees" right="None, Pakka Ghar is free" last />
      </List>
      {live
        ? <Btn label={live.status === 'accepted' ? 'Accepted: pay your deposit' : 'See your application'} onPress={() => router.push(live.status === 'accepted' ? `/book/${p.id}` : '/stay')} />
        : p.rooms.length > 0 && <Btn label="Apply to stay" onPress={() => go('book', `/apply/${p.id}`)} />}
      <Btn kind="secondary" label="Schedule a tour" onPress={() => go('visit', `/tour/${p.id}`)} />
      <T v="sm">Apply alone or with roommates. The owner sees your verified record and accepts; then you pay the deposit in the app. Pakka Ghar is free: no brokerage, no fees.</T>
      {p.photos.length > 0 && map}
    </Screen>
  );
}
