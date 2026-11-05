import { View } from 'react-native';
import { api, ok, useAction, useQuery } from '@/core/api';
import { Badge, Btn, Card, T } from '@/design';

const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', hour12: true }).replace(/\b(AM|PM)\b/g, x => x.toLowerCase());

/* The tenant's upcoming tours, with a way to cancel. */
export function MyTours() {
  const { act, busy } = useAction();
  const tours = useQuery(() => ok(api.GET('/api/visits/mine')));
  const upcoming = (tours.data ?? []).filter(v => ['requested', 'confirmed'].includes(v.status) && new Date(v.slot) > new Date());
  return (
    <>
      {upcoming.length > 0 && <T v="label">Tours</T>}
      {upcoming.map(v => (
        <Card key={v.id}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><T v="bodyBold">{v.name}</T><Badge label={v.status === 'confirmed' ? 'Confirmed' : 'Requested'} tone={v.status === 'confirmed' ? 'ok' : 'warn'} /></View>
          <T v="sm">{when(v.slot)}</T>
          <Btn small kind="ghost" label="Cancel tour" disabled={busy} onPress={() => act(() => ok(api.POST('/api/visits/{visit_id}/cancel', { params: { path: { visit_id: v.id } } })), 'Tour cancelled.')} />
        </Card>
      ))}
    </>
  );
}
