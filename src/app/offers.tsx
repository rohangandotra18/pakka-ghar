import { View } from 'react-native';
import { Tick } from '@/components/icons';
import { Back, Btn, Card, Hero, Screen, Stars, T } from '@/components/ui';
import { OFFERS } from '@/lib/data';
import { useStore } from '@/lib/store';
import { rupees } from '@/lib/theme';

/* The owner's view of sealed offers on a scarce bed. Unverified tenants can't be accepted. */
export default function Offers() {
  const { s, set, toast } = useStore();
  if (!s.offersOpen) return (
    <Screen><Back /><Hero icon={<Tick />} title={`Accepted ${s.acceptedOffer}`} body="They have 24 hours to pay the deposit in the app and sign. The other offers were declined politely, and those people were shown similar PGs nearby." /></Screen>
  );
  return (
    <Screen>
      <Back />
      <T v="h2">Offers · Room 104, bed 3</T>
      <T v="sm">Listed at ₹9,000 · closes Friday 6 pm · capped at ₹10,350</T>
      {OFFERS.map(o => (
        <Card key={o.name}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">{o.name}</T><T v="price">{rupees(o.amount)}</T></View>
          <T v="sm">{o.months} months · moves in {o.moveIn} · {o.verified ? 'verified' : 'not verified yet'}</T>
          {o.pastStays ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Stars value={o.score ?? 0} /><T v="sm">{o.score} from {o.pastStays} past owner{o.pastStays > 1 ? 's' : ''}</T></View> : <T v="sm">No rental history yet</T>}
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small style={{ flex: 1 }} label="Accept" disabled={!o.verified} onPress={() => set({ offersOpen: false, acceptedOffer: o.name })} />
            <Btn small kind="secondary" style={{ flex: 1 }} label="Message" onPress={() => toast(`Chat opened with ${o.name.split(' ')[0]}.`)} />
          </View>
        </Card>
      ))}
      <T v="sm">You can also accept the first booking at the listed rent at any time.</T>
    </Screen>
  );
}
