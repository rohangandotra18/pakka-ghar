import { router } from 'expo-router';
import { View } from 'react-native';
import { api, inr, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { Badge, Btn, Card, T } from './ui';

const STATUS: Record<string, [string, 'ok' | 'warn' | 'crit' | undefined]> = {
  forming: ['Waiting for roommates', 'warn'], pending: ['With the owner', 'warn'], accepted: ['Accepted', 'ok'],
  declined: ['Not this time', 'crit'], withdrawn: ['Withdrawn', undefined],
};
const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', hour12: true }).replace(/\b(AM|PM)\b/g, x => x.toLowerCase());

/* Before a stay: roommate invites, applications (with bid standing) and tours. */
export function TenantPlans() {
  const { act, busy } = useAction();
  const invites = useQuery(() => ok(api.GET('/api/invites')));
  const apps = useQuery(() => ok(api.GET('/api/applications/mine')));
  const tours = useQuery(() => ok(api.GET('/api/visits/mine')));
  const upcoming = (tours.data ?? []).filter(v => ['requested', 'confirmed'].includes(v.status) && new Date(v.slot) > new Date());
  const live = (apps.data ?? []).filter(a => a.status !== 'withdrawn');
  return (
    <>
      {(invites.data ?? []).map(i => (
        <Card key={i.member_id}>
          <T v="bodyBold">{i.from_name} wants you as a roommate</T>
          <T v="sm">{i.name}{i.room ? ` · Room ${i.room}` : ''} · {i.months} months from {new Date(i.move_in_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}{i.amount_paise ? ` · bid ${inr(i.amount_paise)} a bed` : ''}</T>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Btn small style={{ flex: 1 }} label="Join" disabled={busy} onPress={() => act(() => ok(api.POST('/api/invites/{member_id}', { params: { path: { member_id: i.member_id } }, body: { accept: true } })), 'You’re in. It goes to the owner once everyone has joined.')} />
            <Btn small kind="secondary" style={{ flex: 1 }} label="No thanks" disabled={busy} onPress={() => act(() => ok(api.POST('/api/invites/{member_id}', { params: { path: { member_id: i.member_id } }, body: { accept: false } })), `${i.from_name.split(' ')[0]} has been told.`)} />
          </View>
        </Card>
      ))}
      {live.length > 0 && <T v="label">Your applications</T>}
      {live.map(a => {
        const [label, tone] = STATUS[a.status] ?? [a.status, undefined];
        const others = a.members.filter(m => !m.is_lead);
        return (
          <Card key={a.id}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><T v="bodyBold" style={{ flex: 1 }}>{a.name}</T><Badge label={label} tone={tone} /></View>
            <T v="sm">{a.room ? `Room ${a.room}` : 'Any room'} · {a.months} months{a.amount_paise ? ` · your bid ${inr(a.amount_paise)} a bed` : ''}</T>
            {a.amount_paise != null && a.status === 'pending' && <T v="sm">{a.count} bid{a.count === 1 ? '' : 's'} on this room · yours is {a.rank === 1 ? 'the highest' : `number ${a.rank}`} on rent</T>}
            {others.length > 0 && <T v="sm">With {others.map(m => (m.status === 'invited' ? `••${m.phone_last4} (invite sent)` : `${m.name} (${m.status === 'joined' ? 'joined' : m.status === 'declined' ? 'said no' : m.status})`)).join(', ')}</T>}
            {a.status === 'declined' && a.decline_reason ? <T v="sm">“{a.decline_reason}”</T> : null}
            {a.status === 'accepted' && <Btn label="Pay deposit and sign" onPress={() => router.push(`/book/${a.listing}`)} />}
            {a.is_lead && ['forming', 'pending'].includes(a.status) && <>
              {others.filter(m => m.status === 'declined').map(m => (
                <Btn key={m.id} small kind="secondary" label={`Go ahead without ${m.name === 'Invited' ? `••${m.phone_last4}` : m.name.split(' ')[0]}`} disabled={busy}
                  onPress={() => act(() => ok(api.POST('/api/applications/{app_id}/members/{member_id}/remove', { params: { path: { app_id: a.id, member_id: m.id } } })))} />
              ))}
              <Btn small kind="ghost" label="Withdraw" disabled={busy} onPress={() => act(() => ok(api.POST('/api/applications/{app_id}/withdraw', { params: { path: { app_id: a.id } } })), 'Application withdrawn.')} />
            </>}
          </Card>
        );
      })}
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
