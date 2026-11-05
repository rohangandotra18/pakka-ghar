import { router } from 'expo-router';
import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Loading } from '@/components/Loading';
import { SignupPrompt } from '@/components/SignupPrompt';
import { Badge, Btn, Card, Screen, T } from '@/components/ui';
import { api, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { useStore } from '@/lib/store';
import { C } from '@/lib/theme';

const STAGES = ['Raised', 'Assigned', 'Fixed', 'Confirmed'];
export default function Requests() {
  const { tenantReady } = useStore();
  const { act, busy } = useAction();
  const q = useQuery(() => (tenantReady ? ok(api.GET('/api/requests/mine')) : Promise.resolve([])), [tenantReady]);
  const stay = useQuery(() => (tenantReady ? ok(api.GET('/api/stay')) : Promise.resolve({ stay: null })), [tenantReady]);
  if (!tenantReady) return <SignupPrompt title="Maintenance and listing issues" body="Residents raise repairs and report listing problems here. Sign up to report a listing you’ve seen." />;
  const list = q.data;
  return (
    <Screen>
      <AppBar />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><T v="h2">Requests</T><Btn small label="+ New request" onPress={() => router.push('/request-new')} /></View>
      {!list && <Loading error={q.error} retry={q.reload} />}
      {list?.length === 0 && <Card><T v="bodyBold">No requests yet</T><T v="sm">{stay.data?.stay?.moved_in ? 'Raise a repair and the owner sees it at once.' : 'Once you live in a PG, raise repairs here. You can report a listing issue or a request to pay cash at any time.'}</T></Card>}
      {list?.map(r => (
        <Card key={r.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">{r.category}</T><Badge label={r.to_pakka_ghar ? (r.status === 'Raised' ? 'With Pakka Ghar' : 'Resolved') : r.status} tone={r.status === 'Fixed' || r.status === 'Confirmed' ? 'ok' : 'warn'} /></View>
          <T>{r.text}</T>
          {!r.to_pakka_ghar && <View style={{ flexDirection: 'row', gap: 4 }}>{STAGES.map((st, i) => <View key={st} style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: i <= STAGES.indexOf(r.status) ? C.accent : C.line }} />)}</View>}
          <T v="sm">{r.to_pakka_ghar ? 'Sent to the Pakka Ghar trust team, not the owner' : r.assignee ? `Assigned to ${r.assignee}` : 'Waiting for the owner'}</T>
          {r.status === 'Fixed' && !r.to_pakka_ghar && <Btn small label="Confirm it's fixed" disabled={busy} onPress={() => act(() => ok(api.POST('/api/requests/{ticket_id}/confirm', { params: { path: { ticket_id: r.id } } })), 'Thanks. The request is closed.')} />}
        </Card>
      ))}
    </Screen>
  );
}
