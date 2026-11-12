import { Platform, View } from 'react-native';
import { router, useLocalSearchParams, type Href } from 'expo-router';
import Head from 'expo-router/head';
import { MapView } from '@/shared';
import { Loading, Back, Columns, Screen, GENDER_COLOR, SP, useWide } from '@/design';
import { api, ok, useQuery } from '@/core/api';
import { useStore } from '@/core/session';
import { ListingGallery, ListingPhotoNote } from './ListingGallery';
import { ListingActions, ListingBookingPanel, ListingExplainer, ListingFacts, ListingRooms, ListingTitle, ListingWhere } from './ListingParts';

export default function PGDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { tenantReady } = useStore();
  const wide = useWide();
  const q = useQuery(() => ok(api.GET('/api/listings/{slug}', { params: { path: { slug: id } } })), [id]);
  const mine = useQuery(() => (tenantReady ? ok(api.GET('/api/applications/mine')) : Promise.resolve([])), [tenantReady]);
  /* browsing is open; acting needs a verified account. Sign-up then carries straight on to `next`. */
  const go = (why: string, next: string) => {
    if (!tenantReady) router.push({ pathname: '/onboarding/tenant', params: { why, next, listing: id } });
    else router.push(next as Href);
  };
  const p = q.data;
  if (!p) return <Screen width="wide"><Back /><Loading error={q.error} retry={q.reload} /></Screen>;
  const live = (mine.data ?? []).find(a => a.listing === p.id && ['forming', 'pending', 'accepted'].includes(a.status));
  const pinLabel = '₹' + Math.round(p.rent_paise / 100000 * 10) / 10 + 'k';
  const mapAt = (height: number) => <MapView height={height} center={{ lat: p.lat, lng: p.lng }} zoom={15} pins={[{ id: p.id, lat: p.lat, lng: p.lng, label: pinLabel, color: GENDER_COLOR[p.gender] }]} />;
  const hasPhotos = p.photos.length > 0;

  if (wide) {
    return (
      <Screen width="wide">
        {Platform.OS === 'web' && <Head><title>{`${p.name} · ${p.area} · Pakka Ghar`}</title></Head>}
        <Back />
        <ListingGallery photos={p.photos} pgName={p.name} fallback={mapAt(380)} />
        {hasPhotos && <ListingPhotoNote />}
        <View style={{ height: SP.sm }} />
        <Columns side={<ListingBookingPanel p={p} live={live} go={go} />} sideWidth={360} gap={32}>
          <ListingTitle p={p} />
          <ListingRooms p={p} live={live} go={go} />
          <ListingFacts p={p} />
          <ListingWhere p={p} map={mapAt(340)} />
          <ListingExplainer />
        </Columns>
      </Screen>
    );
  }
  return (
    <Screen width="wide">
      <Back />
      <ListingGallery photos={p.photos} pgName={p.name} fallback={mapAt(190)} />
      <ListingTitle p={p} />
      {hasPhotos && <ListingPhotoNote />}
      <ListingRooms p={p} live={live} go={go} />
      <ListingFacts p={p} />
      <ListingActions p={p} live={live} go={go} />
      <ListingExplainer />
      {hasPhotos && mapAt(190)}
    </Screen>
  );
}
