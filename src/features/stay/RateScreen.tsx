import { useState } from 'react';
import { router } from 'expo-router';
import { Tick, Back, Btn, Field, Hero, List, Note, Row, Screen, StarInput, T } from '@/design';
import { api, inr, ok, useAction, useQuery } from '@/core/api';

/* End-of-stay rating. Both sides' ratings unlock together, so neither rates in reaction to the other. */
const ASPECTS = ['Cleanliness', 'Food', 'Owner response', 'Value'] as const;
export default function Rate() {
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/stay')));
  const [v, setV] = useState<Record<string, number>>({});
  const [comment, setComment] = useState('');
  const [done, setDone] = useState(false);
  const allRated = ASPECTS.every(a => (v[a] ?? 0) > 0);
  if (done) return (
    <Screen><Back /><Hero icon={<Tick />} title="Thanks for rating" body="Your rating shows on the PG's page once the owner rates you too, or after 14 days. The owner settles your deposit within 7 days; if they don’t, it comes back to you automatically." /><Btn label="See your rental history" onPress={() => router.replace('/history')} /></Screen>
  );
  const st = q.data?.stay;
  return (
    <Screen>
      <Back />
      <T v="h2">Rate your stay</T>
      <T v="sm">{st ? `${st.booking.name} · since ${st.since}` : 'Your last stay'}</T>
      <List>{ASPECTS.map((a, i) => <Row key={a} last={i === ASPECTS.length - 1} left={a} right={<StarInput value={v[a] ?? 0} onChange={n => setV({ ...v, [a]: n })} />} />)}</List>
      <Field label="Anything to tell future residents?" multiline value={comment} onChangeText={setComment} placeholder="Food, cleanliness, Wi-Fi, how the owner responds…" />
      {st && st.leave_now_charge_paise > 0 && <Note tone="warn">Your notice runs until {new Date(st.notice_ends_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' })}. Leaving today, {inr(st.leave_now_charge_paise)} rent for the days not served comes from your {inr(st.booking.deposit_paise)} deposit.{st.leaves_on ? '' : ' To leave with nothing taken, give notice from My stay and stay until it ends.'}</Note>}
      <Btn label={st && st.leave_now_charge_paise > 0 ? `End stay today (${inr(st.leave_now_charge_paise)} from deposit)` : 'Submit rating and end stay'} disabled={!allRated || !st || busy} onPress={() => act(async () => {
        await ok(api.POST('/api/stay/end', { body: { aspects: v, comment }   /* the deposit is settled after this, so it isn't rated here */ }));
        setDone(true);
      })} />
      {!allRated && <T v="sm">Rate all four to submit.</T>}
      {q.data && !st && <T v="sm">There is no current stay to rate.</T>}
    </Screen>
  );
}
