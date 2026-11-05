import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { Loading, Back, Badge, Btn, List, Note, Row, Screen, T } from '@/design';
import { api, inr, ok, useAction, useQuery } from '@/core/api';

export default function Resident() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/owner/residents/{booking_id}', { params: { path: { booking_id: id } } })), [id]);
  const r = q.data;
  if (!r) return <Screen><Back /><Loading error={q.error} retry={q.reload} /></Screen>;
  const path = { params: { path: { booking_id: r.booking_id } } };
  const pv = r.police;
  const ended = r.status === 'ended' || r.status === 'cancelled';
  return (
    <Screen>
      <Back />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><T v="h2">{r.name}</T><Badge label={`Room ${r.room}`} /></View>
      <List>
        <Row left="Identity" right={<Badge label={r.identity} tone={r.identity === 'Aadhaar verified' ? 'ok' : 'warn'} />} />
        <Row left="Police verification" right={<Badge label={pv} tone={pv === 'Verified' ? 'ok' : pv === 'Submitted' ? 'warn' : 'crit'} />} />
        <Row left="Agreement" right={r.agreement} />
        <Row left="Rent" right={`${inr(r.rent_paise)} · ${r.autopay ? 'AutoPay' : 'UPI'}`} />
        <Row left="Deposit" right={ended ? (r.deposit_outcome || '—') : `${inr(r.deposit_held_paise || r.deposit_paise)} in escrow`} />
        <Row left={ended ? 'Stayed' : 'Since'} right={r.since} last />
      </List>
      {r.leaves_on && <Note tone="soft">Gave notice. Leaves on {new Date(r.leaves_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' })}.</Note>}
      {r.police_missing.length > 0 && pv === 'Not started' && <Note tone="warn">The police form still needs: {r.police_missing.join(', ')}. Ask {r.name.split(' ')[0]} to add them in the app.</Note>}
      {!ended && pv === 'Not started' && <Btn label="Submit police verification" disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/residents/{booking_id}/police/submit', path)), 'Police verification submitted.')} />}
      {!ended && pv === 'Submitted' && <Btn label="Police confirmed: mark verified" disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/residents/{booking_id}/police/verified', path)), 'Police verification: verified.')} />}
      {r.agreement === 'Waiting for your signature' && <Btn label="Read and sign the agreement" onPress={() => router.push(`/agreement/${r.booking_id}`)} />}
      {ended && r.deposit_held_paise > 0 && <Btn label={`Return ${inr(r.deposit_held_paise)} deposit and rate 5 stars`} disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/residents/{booking_id}/move-out', { ...path, body: { deduction_paise: 0, reason: '', rating: 5 } })), 'Deposit returned from escrow. Rating saved.')} />}
      <Btn kind="secondary" label="Open the agreement" onPress={() => router.push(`/agreement/${r.booking_id}`)} />
    </Screen>
  );
}
