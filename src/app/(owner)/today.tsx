import { router, type Href } from 'expo-router';
import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Loading } from '@/components/Loading';
import { Btn, Chip, Kpi, List, Note, Row, Screen, T } from '@/components/ui';
import { api, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';

export default function Today() {
  const { act } = useAction();
  const q = useQuery(() => ok(api.GET('/api/owner/today')));
  const t = q.data;
  /* each to-do either opens a screen or does the job in place */
  const run = (action: string) => {
    if (action === 'send_bills') return act(() => ok(api.POST('/api/owner/bills/send')), 'Bills sent. Residents see their meter reading and pay with rent.');
    const [kind, id] = action.split(':');
    if (kind === 'sign') return router.push(`/agreement/${id}`);
    if (kind === 'visit') return act(() => ok(api.POST('/api/owner/visits/{visit_id}/confirm', { params: { path: { visit_id: id } } })), 'Visit confirmed. They have been told.');
  };
  return (
    <Screen>
      <AppBar />
      {!t ? <Loading error={q.error} retry={q.reload} /> : <>
        <T v="h2">{t.greeting}, {t.owner_name}</T>
        {t.property_status === 'submitted' && <Note tone="soft">{t.property} is with the Pakka Ghar trust team. They check your papers within two working days, then tenants can find it.</Note>}
        {t.property_status === 'draft' && <><Note tone="warn">{t.review_note ? `The trust team sent ${t.property} back: ${t.review_note} Fix it and send it again.` : `${t.property} isn’t live yet. Finish setting it up and send it for checking.`}</Note><Btn small kind="secondary" label="Finish setup" onPress={() => router.push('/onboarding/owner')} /></>}
        {t.property_status === 'paused' && <Note tone="warn">{t.property} is paused after a confirmed report. Contact the trust team to restore it.</Note>}
        <View style={{ flexDirection: 'row', gap: 8 }}><Kpi n={`${t.beds_filled}/${t.beds_total}`} t="Beds filled" /><Kpi n={String(t.rent_unpaid)} t="Bills unpaid" alert={t.rent_unpaid > 0} /></View>
        <View style={{ flexDirection: 'row', gap: 8 }}><Kpi n={String(t.applications)} t="Requests to stay" alert={t.applications > 0} /><Kpi n={String(t.open_requests)} t="Open repairs" alert={t.open_requests > 0} /></View>
        <T v="label">To do</T>
        {t.todos.length === 0 ? <T v="sm">Nothing needs you today.</T> :
          <List>{t.todos.map((x, i) => <Row key={x.key} last={i === t.todos.length - 1} left={x.text} right={<Chip label={x.label} onPress={() => (x.route ? router.push(x.route as Href) : x.action ? run(x.action) : undefined)} />} />)}</List>}
      </>}
    </Screen>
  );
}
