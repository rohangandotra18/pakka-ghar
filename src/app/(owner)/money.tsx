import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Loading } from '@/components/Loading';
import { Badge, Btn, Chip, Kpi, List, Note, Row, Screen, T } from '@/components/ui';
import { api, inr, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';

export default function Money() {
  const { act, busy } = useAction();
  const q = useQuery(() => ok(api.GET('/api/owner/money')));
  const m = q.data;
  if (!m) return <Screen><AppBar /><Loading error={q.error} retry={q.reload} /></Screen>;
  const month = new Date(m.period).toLocaleString('en-IN', { month: 'long' });
  const read = m.read_on ? new Date(m.read_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : null;
  return (
    <Screen>
      <AppBar />
      <T v="h2">{month}</T>
      <View style={{ flexDirection: 'row', gap: 8 }}><Kpi n={inr(m.collected_paise)} t="Collected in the app" /><Kpi n={inr(m.due_paise)} t="Due · rent + electricity" /></View>
      <T v="label">Residents</T>
      <List>
        {m.rows.map((r, i) => (
          <Row key={r.booking_id} last={i === m.rows.length - 1}
            left={<View><T v="bodyBold">{r.name}</T><T v="sm">Room {r.room} · {r.units} units · {r.autopay ? 'AutoPay' : 'UPI'}</T></View>}
            right={r.paid ? <Badge label="Paid" tone="ok" /> : r.autopay ? <Badge label="AutoPay on the 1st" /> : r.reminded ? <Badge label="Reminded" /> : <Chip label="Remind" onPress={() => act(() => ok(api.POST('/api/owner/money/{invoice_id}/remind', { params: { path: { invoice_id: r.invoice_id } } })), `Reminder sent to ${r.name.split(' ')[0]} in the app and on WhatsApp.`)} />} />
        ))}
      </List>
      <Note tone="soft">Rent counts as paid only when it arrives through the app. Cash can’t be recorded.</Note>
      {m.rooms.length > 0 && <>
        <T v="label">Electricity by room{m.bills_sent ? '' : ' · not sent yet'}</T>
        <List>{m.rooms.map((r, i) => <Row key={r.room} last={i === m.rooms.length - 1} left={`Room ${r.room} · ${r.units} units`} right={inr(r.amount_paise)} />)}</List>
        <T v="sm">{read ? `Read from the meters on ${read}` : 'Read from the meters'} at ₹{(m.tariff_paise / 100).toFixed(2)}/unit. Residents saw the same readings.</T>
        {!m.bills_sent && <Btn kind="secondary" label={`Send ${month} electricity bills`} disabled={busy} onPress={() => act(() => ok(api.POST('/api/owner/bills/send')), 'Bills sent. Residents see their meter reading and pay with rent.')} />}
      </>}
      <List>
        <Row left="Deposits in escrow" right={inr(m.escrow_paise)} />
        <Row left="Next payout" right={`${inr(m.next_payout_paise)} · ${m.payout_account ?? 'add a bank account'}`} last />
      </List>
      <Btn kind="secondary" label="Year statement for your CA" disabled={busy} onPress={() => act(() => ok(api.GET('/api/owner/statement')), s => `FY ${s.fy}: rent ${inr(s.rent_paise)}, electricity ${inr(s.electricity_paise)}. ${s.note.split('.')[0]}.`)} />
    </Screen>
  );
}
