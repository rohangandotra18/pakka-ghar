import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Badge, Btn, Card, Screen, T } from '@/components/ui';
import { ASSIGNEE, useStore } from '@/lib/store';

export default function Tickets() {
  const { s, set, toast } = useStore();
  const update = (id: string, status: 'Assigned' | 'Fixed', to?: string) => set(p => ({ ownerRequests: p.ownerRequests.map(r => (r.id === id ? { ...r, status, to: to ?? r.to } : r)) }));
  return (
    <Screen>
      <AppBar />
      <T v="h2">Requests</T>
      {s.ownerRequests.map(r => (
        <Card key={r.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">{r.cat} · Room {r.room}</T><Badge label={r.status} tone={r.status === 'Fixed' ? 'ok' : r.status === 'Assigned' ? 'warn' : 'crit'} /></View>
          <T>{r.text}</T>
          <T v="sm">{r.who} · {r.at}{r.to ? ` · ${r.to}` : ''}</T>
          {r.status === 'Raised' && <Btn small label={`Assign ${(ASSIGNEE[r.cat] ?? 'Caretaker').split(' (')[0]}`} onPress={() => { update(r.id, 'Assigned', ASSIGNEE[r.cat] ?? 'Caretaker'); toast("Assigned. The resident can see who's coming."); }} />}
          {r.status === 'Assigned' && <Btn small label="Mark fixed" onPress={() => { update(r.id, 'Fixed'); toast('Marked fixed. The resident is asked to confirm.'); }} />}
        </Card>
      ))}
      <Card soft><T v="bodyBold">Listing reports</T><T v="sm">None open. Residents can report wrong listing details or a request to pay in cash. A confirmed cash report pauses the listing.</T></Card>
    </Screen>
  );
}
