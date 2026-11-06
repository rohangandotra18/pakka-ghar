import { router } from 'expo-router';
import { View } from 'react-native';
import { api, inr, ok, useAction, useQuery } from '@/core/api';
import { Badge, Btn, Card, T } from '@/design';

const STATUS: Record<string, [string, 'ok' | 'warn' | 'crit' | undefined]> = {
  forming: ['Waiting for roommates', 'warn'], pending: ['With the owner', 'warn'], accepted: ['Accepted', 'ok'],
  declined: ['Not this time', 'crit'], withdrawn: ['Withdrawn', undefined],
};

/* Before a stay: roommate invites and the tenant's applications, with where each bid stands. */
export function MyApplications() {
  const { act, busy } = useAction();
  const invites = useQuery(() => ok(api.GET('/api/invites')));
  const apps = useQuery(() => ok(api.GET('/api/applications/mine')));
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
        /* once accepted, what matters is this person's own held bed: paid, still held, or the 24 hours ran out */
        const lapsed = a.status === 'accepted' && ['expired', 'cancelled'].includes(a.my_booking_status ?? '');
        const [label, tone] = lapsed ? (['Hold ran out', 'crit'] as const) : STATUS[a.status] ?? [a.status, undefined];
        const others = a.members.filter(m => !m.is_lead);
        return (
          <Card key={a.id}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><T v="bodyBold" style={{ flex: 1 }}>{a.name}</T><Badge label={label} tone={tone} /></View>
            <T v="sm">{a.room ? `Room ${a.room}` : 'Any room'} · {a.months} months{a.amount_paise ? ` · your bid ${inr(a.amount_paise)} a bed` : ''}</T>
            {a.amount_paise != null && a.status === 'pending' && <T v="sm">{a.count} bid{a.count === 1 ? '' : 's'} on this room · yours is {a.rank === 1 ? 'the highest' : `number ${a.rank}`} on rent</T>}
            {others.length > 0 && <T v="sm">With {others.map(m => (m.status === 'invited' ? `••${m.phone_last4} (invite sent)` : `${m.name} (${m.status === 'joined' ? 'joined' : m.status === 'declined' ? 'said no' : m.status})`)).join(', ')}</T>}
            {a.status === 'declined' && a.decline_reason ? <T v="sm">“{a.decline_reason}”</T> : null}
            {a.status === 'accepted' && a.my_booking_status === 'hold' && <Btn label="Pay deposit and sign" onPress={() => router.push(`/book/${a.listing}`)} />}
            {lapsed && <>
              <T v="sm">The deposit wasn’t paid within 24 hours, so the bed was released. Apply again if it’s still free.</T>
              <Btn small kind="secondary" label="Apply again" onPress={() => router.push(`/apply/${a.listing}`)} />
            </>}
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
    </>
  );
}
