import { useState } from 'react';
import { View } from 'react-native';
import { AppBar } from '@/shared';
import { Loading, Badge, Btn, Card, Field, Screen, T } from '@/design';
import { api, ok, useAction, useQuery } from '@/core/api';

const when = (iso: string) => {
  const d = new Date(iso), days = Math.floor((Date.now() - d.getTime()) / 86400000);
  const hm = d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: false });
  return days === 0 ? `Today ${hm}` : days === 1 ? 'Yesterday' : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
};

export default function Tickets() {
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/owner/tickets')));
  /* who the owner is sending, per request; blank means their saved contact for that kind of repair */
  const [who, setWho] = useState<Record<string, string>>({});
  return (
    <Screen>
      <AppBar />
      <T v="h2">Requests</T>
      {!q.data && <Loading error={q.error} retry={q.reload} />}
      {q.data?.length === 0 && <Card><T v="sm">No requests. Residents raise repairs here and you assign someone.</T></Card>}
      {q.data?.map(r => (
        <Card key={r.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">{r.category} · Room {r.room}</T><Badge label={r.status} tone={r.status === 'Fixed' || r.status === 'Confirmed' ? 'ok' : r.status === 'Assigned' ? 'warn' : 'crit'} /></View>
          <T>{r.text}</T>
          <T v="sm">{r.who} · {when(r.at)}{r.assignee ? ` · ${r.assignee}` : ''}</T>
          {r.status === 'Raised' && <>
            <Field label="Who's coming?" value={who[r.id] ?? ''} onChangeText={t => setWho(m => ({ ...m, [r.id]: t }))} placeholder={`${r.suggested_assignee} (name and number)`} />
            <Btn small label="Assign" disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/tickets/{ticket_id}/assign', { params: { path: { ticket_id: r.id } }, body: { assignee: who[r.id]?.trim() || null } })), "Assigned. The resident can see who's coming.")} />
          </>}
          {r.status === 'Assigned' && <Btn small label="Mark fixed" disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/tickets/{ticket_id}/fixed', { params: { path: { ticket_id: r.id } } })), 'Marked fixed. The resident is asked to confirm.')} />}
        </Card>
      ))}
      <Card soft><T v="bodyBold">Listing reports</T><T v="sm">Residents can report wrong listing details or a request to pay in cash. Those go to the Pakka Ghar trust team; a confirmed cash report pauses the listing.</T></Card>
    </Screen>
  );
}
