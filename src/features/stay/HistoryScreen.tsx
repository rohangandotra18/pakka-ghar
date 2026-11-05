import { View } from 'react-native';
import { AppBar, SignupPrompt } from '@/shared';
import { Loading, Badge, Card, Screen, Stars, T } from '@/design';
import { api, inr, ok, useQuery } from '@/core/api';
import { useStore } from '@/core/session';

/* Every place the tenant has rented through Pakka Ghar. Owners see this record when the tenant makes an offer. */
export default function History() {
  const { tenantReady } = useStore();
  const q = useQuery(() => (tenantReady ? ok(api.GET('/api/history')) : Promise.resolve(null)), [tenantReady]);
  if (!tenantReady) return <SignupPrompt title="Your rental history" body="Every place you rent through Pakka Ghar is kept here, with your ratings. A good record helps you win offers on popular PGs." />;
  const h = q.data;
  return (
    <Screen>
      <AppBar />
      <T v="h2">Your rental history</T>
      <T v="sm">Every place you’ve stayed through Pakka Ghar.</T>
      {!h && <Loading error={q.error} retry={q.reload} />}
      {h && h.items.length === 0 && <Card><T v="sm">Nothing yet. Your first booking starts your record.</T></Card>}
      {h?.items.map((x, i) => (
        <Card key={x.booking_id ?? i}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><T v="bodyBold">{x.name}</T>{x.current ? <Badge label="Current" tone="ok" /> : <Stars value={x.rated ?? 0} />}</View>
          <T v="sm">{x.area} · {x.from_label} – {x.to_label} · {inr(x.rent_paise)}/month</T>
          {x.deposit ? <T v="sm" style={{ color: '#111714' }}>{x.deposit}</T> : null}
        </Card>
      ))}
      {h && <Card soft>
        <T v="bodyBold">Your resident rating</T>
        {h.score != null
          ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Stars value={h.score} /><T v="sm">{h.score} from {h.rated_by} owner{h.rated_by === 1 ? '' : 's'}</T></View>
          : <T v="sm">No owner has rated you yet.</T>}
        <T v="sm">On-time rent, room condition at move-out, and notice given.</T>
      </Card>}
    </Screen>
  );
}
