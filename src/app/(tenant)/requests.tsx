import { router } from 'expo-router';
import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { SignupPrompt } from '@/components/SignupPrompt';
import { Badge, Btn, Card, Screen, T } from '@/components/ui';
import { useStore } from '@/lib/store';
import { C } from '@/lib/theme';

const STAGES = ['Raised', 'Assigned', 'Fixed', 'Confirmed'] as const;
export default function Requests() {
  const { s, set } = useStore();
  if (!s.tenantReady) return <SignupPrompt title="Maintenance and listing issues" body="Residents raise repairs and report listing problems here. Sign up to report a listing you’ve seen." next="/requests" />;
  return (
    <Screen>
      <AppBar />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><T v="h2">Requests</T><Btn small label="+ New request" onPress={() => router.push('/request-new')} /></View>
      {s.myRequests.length === 0 && <Card><T v="bodyBold">No requests yet</T><T v="sm">{s.stay ? 'Raise a repair and the owner sees it at once.' : 'Once you live in a PG, raise repairs here. You can report a listing issue or a request to pay cash at any time.'}</T></Card>}
      {s.myRequests.map(r => (
        <Card key={r.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">{r.cat}</T><Badge label={r.status} tone={r.status === 'Fixed' || r.status === 'Confirmed' ? 'ok' : 'warn'} /></View>
          <T>{r.text}</T>
          <View style={{ flexDirection: 'row', gap: 4 }}>{STAGES.map((st, i) => <View key={st} style={{ flex: 1, height: 4, borderRadius: 2, backgroundColor: i <= STAGES.indexOf(r.status) ? C.accent : C.line }} />)}</View>
          <T v="sm">{r.to ? `Assigned to ${r.to}` : 'Waiting for the owner'}</T>
          {r.status === 'Fixed' && <Btn small label="Confirm it's fixed" onPress={() => set(p => ({ myRequests: p.myRequests.map(x => (x.id === r.id ? { ...x, status: 'Confirmed' } : x)) }))} />}
        </Card>
      ))}
    </Screen>
  );
}
