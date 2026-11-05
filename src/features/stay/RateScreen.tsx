import { useState } from 'react';
import { router } from 'expo-router';
import { TextInput } from 'react-native';
import { Tick, Back, Btn, Chip, Chips, Hero, List, Row, Screen, StarInput, T, C, F } from '@/design';
import { api, ok, useAction, useQuery } from '@/core/api';

/* End-of-stay rating. Both sides' ratings unlock together, so neither rates in reaction to the other. */
const ASPECTS = ['Cleanliness', 'Food', 'Owner response', 'Value'] as const;
export default function Rate() {
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/stay')));
  const [v, setV] = useState<Record<string, number>>({});
  const [dep, setDep] = useState('Yes');
  const [comment, setComment] = useState('');
  const [done, setDone] = useState(false);
  const allRated = ASPECTS.every(a => (v[a] ?? 0) > 0);
  if (done) return (
    <Screen><Back /><Hero icon={<Tick />} title="Thanks for rating" body="Your rating shows on the PG's page once the owner rates you too, or after 14 days. Your deposit refund is being processed from escrow." /><Btn label="See your rental history" onPress={() => router.replace('/history')} /></Screen>
  );
  const st = q.data?.stay;
  return (
    <Screen>
      <Back />
      <T v="h2">Rate your stay</T>
      <T v="sm">{st ? `${st.booking.name} · since ${st.since}` : 'Your last stay'}</T>
      <List>{ASPECTS.map((a, i) => <Row key={a} last={i === ASPECTS.length - 1} left={a} right={<StarInput value={v[a] ?? 0} onChange={n => setV({ ...v, [a]: n })} />} />)}</List>
      <T v="label">Deposit returned on time?</T>
      <Chips>{['Yes', 'No'].map(c => <Chip key={c} label={c} on={dep === c} onPress={() => setDep(c)} />)}</Chips>
      <T v="label">Anything to tell future residents?</T>
      <TextInput allowFontScaling={false} multiline value={comment} onChangeText={setComment} placeholder="Food, cleanliness, Wi-Fi, how the owner responds…" placeholderTextColor={C.muted} style={{ minHeight: 90, borderWidth: 1, borderColor: C.line, borderRadius: 11, backgroundColor: C.surface, padding: 12, fontFamily: F.semi, fontSize: 15, color: C.ink, textAlignVertical: 'top' }} />
      <Btn label="Submit rating and end stay" disabled={!allRated || !st || busy} onPress={() => act(async () => {
        await ok(api.POST('/api/stay/end', { body: { aspects: v, deposit_on_time: dep === 'Yes', comment } }));
        setDone(true);
      })} />
      {!allRated && <T v="sm">Rate all four to submit.</T>}
      {q.data && !st && <T v="sm">There is no current stay to rate.</T>}
    </Screen>
  );
}
