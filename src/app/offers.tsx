import { View } from 'react-native';
import { Tick } from '@/components/icons';
import { Loading } from '@/components/Loading';
import { Back, Btn, Card, Hero, Screen, Stars, T } from '@/components/ui';
import { api, inr, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { useStore } from '@/lib/store';

/* The owner's view of sealed offers on a scarce bed. Unverified tenants can't be accepted. */
export default function Offers() {
  const { toast } = useStore();
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/owner/offers')));
  const b = q.data;
  if (!b) return <Screen><Back /><Loading error={q.error} retry={q.reload} /></Screen>;
  if (!b.open && b.accepted) return (
    <Screen><Back /><Hero icon={<Tick />} title={`Accepted ${b.accepted}`} body="They have 24 hours to pay the deposit in the app and sign. The other offers were declined politely, and those people were shown similar PGs nearby." /></Screen>
  );
  if (!b.bed_id) return <Screen><Back /><T v="h2">No offers open</T><T v="sm">When a bed is in high demand, you can take sealed offers on it instead of the first booking.</T></Screen>;
  const closes = b.closes_at ? new Date(b.closes_at).toLocaleString('en-IN', { weekday: 'long', hour: 'numeric', hour12: true }).toLowerCase() : 'Friday 6 pm';
  return (
    <Screen>
      <Back />
      <T v="h2">Offers · Room {b.room}, bed {b.bed}</T>
      <T v="sm">Listed at {inr(b.listed_paise)} · closes {closes} · capped at {inr(b.cap_paise)}</T>
      {b.offers.length === 0 && <Card><T v="sm">No offers yet.</T></Card>}
      {b.offers.map(o => (
        <Card key={o.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">{o.name}</T><T v="price">{inr(o.amount_paise)}</T></View>
          <T v="sm">{o.months} months · moves in {new Date(o.move_in_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} · {o.verified ? 'verified' : 'not verified yet'}</T>
          {o.past_stays && o.score != null ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Stars value={o.score} /><T v="sm">{o.score} from {o.past_stays} past owner{o.past_stays > 1 ? 's' : ''}</T></View> : <T v="sm">No rental history yet</T>}
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small style={{ flex: 1 }} label={o.verified ? 'Accept' : 'ID pending'} disabled={!o.verified || busy} onPress={() => act(() => ok(api.POST('/api/owner/offers/{offer_id}/accept', { params: { path: { offer_id: o.id } } })))} />
            <Btn small kind="secondary" style={{ flex: 1 }} label="Message" onPress={() => toast(`Chat with ${o.name.split(' ')[0]} opens here. Phone numbers stay private.`)} />
          </View>
        </Card>
      ))}
      <Btn kind="ghost" label="Stop taking offers on this bed" disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/beds/{bed_id}/offers', { params: { path: { bed_id: b.bed_id! } }, body: { open: false } })), 'Offers closed. Anyone who offered has been told.')} />
      <T v="sm">Closing offers lets the bed be booked at the listed rent again.</T>
    </Screen>
  );
}
