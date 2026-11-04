import { useState } from 'react';
import { TextInput } from 'react-native';
import { Tick } from '@/components/icons';
import { Back, Btn, Chip, Chips, Hero, List, Row, Screen, StarInput, T } from '@/components/ui';
import { pgById, useStore } from '@/lib/store';
import { C, F } from '@/lib/theme';

/* End-of-stay rating. Both sides' ratings unlock together, so neither rates in reaction to the other. */
const ASPECTS = ['Cleanliness', 'Food', 'Owner response', 'Value'];
export default function Rate() {
  const { s, set } = useStore();
  const [v, setV] = useState<Record<string, number>>({});
  const [dep, setDep] = useState('Yes');
  if (s.rated) return (
    <Screen><Back /><Hero icon={<Tick />} title="Thanks for rating" body="Your rating shows on the PG's page once the owner rates you too, or after 14 days. Your deposit refund is being processed from escrow." /></Screen>
  );
  return (
    <Screen>
      <Back />
      <T v="h2">Rate your stay</T>
      <T v="sm">{s.stay ? `${pgById(s.stay.pgId).name} · ${s.stay.since} – Jan 2027` : 'Your last stay'}</T>
      <List>{ASPECTS.map((a, i) => <Row key={a} last={i === ASPECTS.length - 1} left={a} right={<StarInput value={v[a] ?? 0} onChange={n => setV({ ...v, [a]: n })} />} />)}</List>
      <T v="label">Deposit returned on time?</T>
      <Chips>{['Yes', 'No'].map(c => <Chip key={c} label={c} on={dep === c} onPress={() => setDep(c)} />)}</Chips>
      <T v="label">Anything to tell future residents?</T>
      <TextInput allowFontScaling={false} multiline defaultValue="Clean rooms and good food. Wi-Fi is slow in the evenings." style={{ minHeight: 90, borderWidth: 1, borderColor: C.line, borderRadius: 11, backgroundColor: C.surface, padding: 12, fontFamily: F.semi, fontSize: 15, color: C.ink, textAlignVertical: 'top' }} />
      <Btn label="Submit rating" onPress={() => set({ rated: true })} />
    </Screen>
  );
}
