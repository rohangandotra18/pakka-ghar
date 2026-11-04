import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { SignupPrompt } from '@/components/SignupPrompt';
import { pgById, useStore } from '@/lib/store';
import { Badge, Card, Screen, Stars, T } from '@/components/ui';
import { MY_HISTORY } from '@/lib/data';
import { rupees } from '@/lib/theme';

/* Every place the tenant has rented through Pakka Ghar. Owners see this record when the tenant makes an offer. */
export default function History() {
  const { s } = useStore();
  if (!s.tenantReady) return <SignupPrompt title="Your rental history" body="Every place you rent through Pakka Ghar is kept here, with your ratings. A good record helps you win offers on popular PGs." next="/history" />;
  return (
    <Screen>
      <AppBar />
      <T v="h2">Your rental history</T>
      <T v="sm">Every place you’ve stayed through Pakka Ghar.</T>
      {[...(s.stay ? [{ name: pgById(s.stay.pgId).name, area: pgById(s.stay.pgId).area + ', Chandigarh', from: s.stay.since, to: 'now', rent: s.stay.rent, current: true, rated: undefined as number | undefined, deposit: undefined as string | undefined }] : []), ...MY_HISTORY].map(h => (
        <Card key={h.name}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><T v="bodyBold">{h.name}</T>{h.current ? <Badge label="Current" tone="ok" /> : <Stars value={h.rated ?? 0} />}</View>
          <T v="sm">{h.area} · {h.from} – {h.to} · {rupees(h.rent)}/month</T>
          {h.deposit ? <T v="sm" style={{ color: '#111714' }}>{h.deposit}</T> : null}
        </Card>
      ))}
      <Card soft>
        <T v="bodyBold">Your resident rating</T>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Stars value={4.7} /><T v="sm">4.7 from 2 owners</T></View>
        <T v="sm">On-time rent, room condition at move-out, and notice given.</T>
      </Card>
    </Screen>
  );
}
