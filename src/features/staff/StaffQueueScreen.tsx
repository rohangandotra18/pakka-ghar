import { useState } from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { AppBar } from '@/shared';
import { Badge, Btn, C, Card, Field, Loading, Note, Screen, T } from '@/design';
import { api, ok, useAction, useQuery } from '@/core/api';
import { useStore } from '@/core/session';

const when = (iso: string) => {
  const d = new Date(iso), days = Math.floor((Date.now() - d.getTime()) / 86400000);
  const hm = d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: false });
  return days === 0 ? `Today ${hm}` : days === 1 ? 'Yesterday' : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
};
const titleCase = (s: string) => s.replace(/\b\w/g, c => c.toUpperCase());

/* what each ownership paper is called (the kinds the server keeps) */
const PAPER: Record<string, string> = {
  sale_deed: 'Sale deed or allotment letter', property_tax: 'Property tax receipt',
  pg_registration: 'PG registration', lease: 'Lease that allows subletting',
};
/* a paper is in order once it is uploaded or accepted; "later" means the owner hasn't given it yet (the server
   only insists on a sale deed or lease), so it is a caution, not a failure */
const paperTone = (status: string) => (status === 'uploaded' || status === 'accepted' ? 'ok' : status === 'later' ? 'warn' : 'crit');

const CASH = 'Asked to pay in cash';

export default function StaffQueueScreen() {
  const { s } = useStore();
  const { act, busy } = useAction();
  const me = s.session?.me;
  const q = useQuery(() => (me?.staff ? ok(api.GET('/api/staff/queue')) : Promise.resolve(null)), [me?.staff]);
  /* the one action waiting for its second press, as "kind:id" */
  const [pending, setPending] = useState<string | null>(null);
  const [reason, setReason] = useState<Record<string, string>>({});

  const header = <><AppBar /><T v="h2">Trust team</T></>;
  if (!s.booted) return <Screen>{header}<Loading /></Screen>;
  if (!me) return (
    <Screen>{header}
      <Card>
        <T>Sign in with your trust team number to see what is waiting.</T>
        <Btn label="Sign in" onPress={() => router.push({ pathname: '/onboarding/tenant', params: { why: 'signin' } })} />
      </Card>
    </Screen>
  );
  const denied = (
    <Screen>{header}
      <Card>
        <T>Only the Pakka Ghar trust team can open this.</T>
        <Btn kind="secondary" label="Back to Find" onPress={() => router.replace('/find')} />
      </Card>
    </Screen>
  );
  if (!me.staff || q.error?.code === 'not_staff') return denied;

  const data = q.data;
  const done = (fn: () => Promise<unknown>, msg: string) => act(async () => { const r = await fn(); setPending(null); return r; }, msg);
  const approve = (slug: string) => done(() => ok(api.POST('/api/staff/properties/{slug}/approve', { params: { path: { slug } } })), 'Published. The owner has been told.');
  const sendBack = (slug: string) => done(async () => {
    const r = await ok(api.POST('/api/staff/properties/{slug}/reject', { params: { path: { slug } }, body: { reason: (reason[slug] ?? '').trim() } }));
    setReason(m => { const { [slug]: _gone, ...rest } = m; return rest; });
    return r;
  }, 'Sent back to the owner with your note.');
  const resolve = (id: string, outcome: 'confirmed' | 'dismissed') => done(() => ok(api.POST('/api/staff/reports/{report_id}/resolve', { params: { path: { report_id: id } }, body: { outcome } })),
    outcome === 'confirmed' ? 'Report confirmed.' : 'Report dismissed.');

  const Confirm = ({ text, yes, onYes }: { text: string; yes: string; onYes: () => void }) => (
    <View style={{ gap: 8 }}>
      <T v="bodyBold">{text}</T>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        <Btn small label={yes} disabled={busy} onPress={onYes} />
        <Btn small kind="secondary" label="Cancel" disabled={busy} onPress={() => setPending(null)} />
      </View>
    </View>
  );

  return (
    <Screen>
      {header}
      {!data && <Loading error={q.error} retry={q.reload} />}
      {data && <>
        <T v="h3">PGs waiting for a check ({data.properties.length})</T>
        {data.properties.length === 0 && <Card><T v="sm">Nothing is waiting.</T></Card>}
        {data.properties.map(p => {
          const key = (k: string) => `${k}:${p.id}`;
          const docs = Object.entries(p.documents);
          const text = reason[p.id] ?? '';
          return (
            <Card key={p.id}>
              <T v="bodyBold">{p.name}</T>
              <T v="sm">{titleCase(p.city)} · {p.address}</T>
              <T v="sm">{p.owner || 'Owner'}{p.owner_phone ? ` · ${p.owner_phone}` : ''}</T>
              <T v="sm">Submitted {when(p.submitted_at)} · {p.rooms} {p.rooms === 1 ? 'room' : 'rooms'}, {p.beds} {p.beds === 1 ? 'bed' : 'beds'}</T>
              {!!p.recheck && <Note><T v="bodyBold">Back for a re-check: {p.recheck}</T></Note>}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                <Badge label={p.pinned ? 'Map pin set' : 'No map pin'} tone={p.pinned ? 'ok' : 'crit'} />
                {docs.length === 0 && <Badge label="No ownership papers" tone="crit" />}
                {docs.map(([kind, status]) => <Badge key={kind} label={`${PAPER[kind] ?? kind}: ${status}`} tone={paperTone(status)} />)}
                <Badge label={p.payout ? 'Payout account added' : 'No payout account'} tone={p.payout ? 'ok' : 'crit'} />
                <Badge label={p.no_cash_pledged ? 'No-cash promise made' : 'No-cash promise missing'} tone={p.no_cash_pledged ? 'ok' : 'crit'} />
              </View>
              {pending === key('approve') ? (
                <Confirm text={`Publish ${p.name}?`} yes="Yes, publish" onYes={() => approve(p.id)} />
              ) : pending === key('reject') ? (
                <View style={{ gap: 8 }}>
                  <Field label="What should the owner fix?" multiline value={text} onChangeText={t => setReason(m => ({ ...m, [p.id]: t }))} />
                  <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                    <Btn small label="Send back" disabled={busy || !text.trim()} onPress={() => sendBack(p.id)} />
                    <Btn small kind="secondary" label="Cancel" disabled={busy} onPress={() => setPending(null)} />
                  </View>
                </View>
              ) : (
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  <Btn small label="Approve and publish" disabled={busy} onPress={() => setPending(key('approve'))} />
                  <Btn small kind="secondary" label="Send back" disabled={busy} onPress={() => setPending(key('reject'))} />
                </View>
              )}
            </Card>
          );
        })}

        <T v="h3">Open reports ({data.reports.length})</T>
        {data.reports.length === 0 && <Card><T v="sm">Nothing is waiting.</T></Card>}
        {data.reports.map(r => {
          const key = (k: string) => `${k}:${r.id}`;
          return (
            <Card key={r.id}>
              <T v="bodyBold">{r.category}</T>
              <T>{r.text}</T>
              {!!r.listing && (
                <Pressable accessibilityRole="link" onPress={() => router.push(`/pg/${r.listing}`)} hitSlop={6} style={{ alignSelf: 'flex-start' }}>
                  <T v="smBold" style={{ color: C.accent }}>{r.listing}</T>
                </Pressable>
              )}
              <T v="sm">Reported by {r.reporter} · {when(r.created_at)}</T>
              {pending === key('confirm') ? (
                <Confirm yes="Yes, confirm" onYes={() => resolve(r.id, 'confirmed')}
                  text={r.category === CASH ? 'Confirm this report? That pauses the listing, so tenants can no longer find or book it.' : 'Confirm this report?'} />
              ) : pending === key('dismiss') ? (
                <Confirm text="Dismiss this report? The reporter is told no problem was found." yes="Yes, dismiss" onYes={() => resolve(r.id, 'dismissed')} />
              ) : (
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  <Btn small label="Confirm" disabled={busy} onPress={() => setPending(key('confirm'))} />
                  <Btn small kind="secondary" label="Dismiss" disabled={busy} onPress={() => setPending(key('dismiss'))} />
                </View>
              )}
            </Card>
          );
        })}
      </>}
    </Screen>
  );
}
