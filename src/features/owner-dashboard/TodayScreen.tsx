import { router, type Href } from 'expo-router';
import { Pressable, View, useWindowDimensions } from 'react-native';
import { AppBar } from '@/shared';
import { Loading, Btn, Card, Note, Screen, T, C, R, SP } from '@/design';
import { api, inr, ok, useAction, useQuery } from '@/core/api';

const TONE = { urgent: C.crit, soon: C.warn, normal: C.accent } as const;
const day = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });
const month = (ym: string) => new Date(`${ym}-01`).toLocaleDateString('en-IN', { month: 'short' });
const short = (p: number) => (p >= 10000000 ? `₹${(p / 10000000).toFixed(1)}L` : p >= 100000 ? `₹${Math.round(p / 100000)}k` : inr(p));

/* Home: first what needs the owner (each item acts in place or opens the one screen that does), then how the PG is
   doing: beds, this month's money, six months of collections, and the next 30 days. Same screen on the phone
   (stacked) and the website (two columns). */
export default function Home() {
  const { act, busy } = useAction();
  const { width } = useWindowDimensions();
  const q = useQuery(() => ok(api.GET('/api/owner/today')));
  const t = q.data;
  const wide = width >= 900;
  const run = (action: string) => {
    if (action === 'send_bills') return act(() => ok(api.POST('/api/owner/bills/send')), 'Bills sent. Residents see their meter reading and pay with rent.');
    const [kind, ids] = action.split(':');
    if (kind === 'police') return act(async () => {
      for (const id of ids.split(',')) await ok(api.POST('/api/owner/residents/{booking_id}/police/submit', { params: { path: { booking_id: id } } }));
    }, ids.includes(',') ? 'All police forms submitted.' : 'Police verification submitted.');
    if (kind === 'visit') return act(() => ok(api.POST('/api/owner/visits/{visit_id}/confirm', { params: { path: { visit_id: ids } } })), 'Tour confirmed. They have been told.');
  };
  if (!t) return <Screen><AppBar /><Loading error={q.error} retry={q.reload} /></Screen>;

  const filled = t.beds.filter(b => b.state === 'filled' || b.state === 'leaving').length;
  const pct = t.beds_total ? Math.round((filled / t.beds_total) * 100) : 0;
  const status = t.property_status === 'published' ? 'Live' : t.property_status === 'submitted' ? 'With the trust team' : t.property_status === 'paused' ? 'Paused' : 'Not live yet';

  const kpi = (n: string, label: string, alert?: boolean, onPress?: () => void) => (
    <Pressable key={label} onPress={onPress} disabled={!onPress} accessibilityRole={onPress ? 'button' : undefined}
      style={{ flexGrow: 1, flexBasis: wide ? 0 : '45%', minWidth: 140, backgroundColor: C.surface, borderRadius: R.md, borderWidth: 1, borderColor: alert ? C.crit : C.line, padding: 12, gap: 2 }}>
      <T v="h2" style={{ color: alert ? C.crit : C.ink, fontVariant: ['tabular-nums'] }}>{n}</T>
      <T v="sm" style={{ fontSize: 12 }}>{label}</T>
    </Pressable>
  );

  const needs = (
    <Card>
      <T v="bodyBold">Needs you</T>
      {t.todos.length === 0 ? <T v="sm">Nothing needs you today.</T> : t.todos.map((x, i) => (
        <View key={x.key} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderTopWidth: i ? 1 : 0, borderTopColor: C.line }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: TONE[x.tone as keyof typeof TONE] ?? C.accent }} />
          <T style={{ flex: 1 }}>{x.text}</T>
          <Btn small kind={x.tone === 'urgent' ? 'primary' : 'secondary'} label={x.label} disabled={busy}
            onPress={() => (x.route ? router.push(x.route as Href) : x.action ? run(x.action) : undefined)} />
        </View>
      ))}
    </Card>
  );

  const beds = (
    <Card>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <T v="bodyBold">Beds</T>
        <Pressable onPress={() => router.navigate('/beds')} accessibilityRole="link" hitSlop={14}><T v="smBold" style={{ color: C.accent }}>Open board ›</T></Pressable>
      </View>
      {t.beds.length === 0 ? <T v="sm">No rooms yet.</T> : (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 5 }}>
          {t.beds.map(b => {
            const free = b.state === 'free';
            const bg = free ? 'transparent' : b.state === 'leaving' ? C.warnBg : b.state === 'held' ? C.surface2 : C.accentSoft;
            const fg = b.state === 'leaving' ? C.warn : free ? C.ok : C.accent;
            return (
              <View key={`${b.room}-${b.bed}`} accessibilityLabel={`Room ${b.room} bed ${b.bed}: ${b.state}${b.who ? `, ${b.who}` : ''}`}
                style={{ width: 66, paddingVertical: 6, borderRadius: 7, alignItems: 'center', backgroundColor: bg, borderWidth: free ? 1 : 0, borderColor: C.ok, borderStyle: 'dashed' }}>
                <T v="smBold" style={{ fontSize: 11, color: fg }}>{b.room}·{b.bed}</T>
                <T v="sm" style={{ fontSize: 10, color: fg }} numberOfLines={1}>{b.who ?? 'free'}</T>
              </View>
            );
          })}
        </View>
      )}
      <T v="sm" style={{ fontSize: 11 }}>Filled · <T v="sm" style={{ fontSize: 11, color: C.warn }}>leaving</T> · held for payment · dashed = free</T>
    </Card>
  );

  const max = Math.max(1, ...t.months.map(m => Math.max(m.collected_paise, m.due_paise)));
  const chart = (
    <Card>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <T v="bodyBold">Collected, last 6 months</T>
        <Pressable onPress={() => router.navigate('/money')} accessibilityRole="link" hitSlop={14}><T v="smBold" style={{ color: C.accent }}>Money ›</T></Pressable>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 10, height: 120 }} accessibilityLabel={t.months.map(m => `${month(m.period)} ${inr(m.collected_paise)}`).join(', ')}>
        {t.months.map(m => (
          <View key={m.period} style={{ flex: 1, alignItems: 'center', gap: 4 }}>
            <T v="sm" style={{ fontSize: 10 }}>{m.collected_paise ? short(m.collected_paise) : ''}</T>
            <View style={{ width: '100%', height: 84, justifyContent: 'flex-end' }}>
              {m.due_paise > m.collected_paise && <View style={{ height: (84 * (m.due_paise - m.collected_paise)) / max, backgroundColor: C.line, borderTopLeftRadius: 4, borderTopRightRadius: 4 }} />}
              <View style={{ height: Math.max(m.collected_paise ? 3 : 0, (84 * m.collected_paise) / max), backgroundColor: C.accent, borderRadius: m.due_paise > m.collected_paise ? 0 : 4, borderBottomLeftRadius: 4, borderBottomRightRadius: 4 }} />
            </View>
            <T v="sm" style={{ fontSize: 11 }}>{month(m.period)}</T>
          </View>
        ))}
      </View>
      <T v="sm" style={{ fontSize: 11 }}>Green: paid in the app. Grey: billed, not paid yet.</T>
    </Card>
  );

  const coming = (
    <Card>
      <T v="bodyBold">Coming up</T>
      {t.coming.length === 0 ? <T v="sm">Nothing in the next 30 days.</T> : t.coming.map((c, i) => (
        <View key={`${c.on}-${i}`} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10, paddingVertical: 6, borderTopWidth: i ? 1 : 0, borderTopColor: C.line }}>
          <T style={{ flex: 1 }}>{c.text}</T><T v="sm">{day(c.on)}</T>
        </View>
      ))}
    </Card>
  );

  const col = (children: React.ReactNode) => <View style={{ flex: 1, gap: SP.md, minWidth: 0 }}>{children}</View>;
  return (
    <Screen>
      <AppBar />
      <View style={{ gap: 2 }}>
        <T v="h2">{t.greeting}, {t.owner_name}</T>
        <T v="sm">{t.property}{t.property_area ? ` · ${t.property_area}` : ''} · {status}</T>
      </View>
      {t.property_status === 'submitted' && <Note tone="soft">The trust team checks your papers within two working days, then tenants can find {t.property}.</Note>}
      {t.property_status === 'draft' && <><Note tone="warn">{t.review_note ? `The trust team sent ${t.property} back: ${t.review_note} Fix it and send it again.` : `${t.property} isn’t live yet. Finish setting it up and send it for checking.`}</Note>
        <Btn small kind="secondary" label="Finish setup" onPress={() => router.push('/onboarding/owner')} /></>}
      {t.property_status === 'paused' && <Note tone="warn">{t.property} is paused after a confirmed report. Contact the trust team to restore it.</Note>}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {kpi(`${filled}/${t.beds_total}`, `beds filled${t.beds_total ? ` · ${pct}%` : ''}`, false, () => router.navigate('/beds'))}
        {kpi(inr(t.collected_paise), 'collected this month', false, () => router.navigate('/money'))}
        {kpi(inr(t.unpaid_paise), `${t.unpaid_count} bill${t.unpaid_count === 1 ? '' : 's'} unpaid`, t.unpaid_paise > 0, () => router.navigate('/money'))}
        {kpi(String(t.free_next_month), 'beds free next month', false, () => router.navigate('/beds'))}
      </View>
      {wide
        ? <View style={{ flexDirection: 'row', gap: SP.md, alignItems: 'flex-start' }}>{col(<>{needs}{chart}</>)}{col(<>{beds}{coming}</>)}</View>
        : <>{needs}{beds}{chart}{coming}</>}
    </Screen>
  );
}
