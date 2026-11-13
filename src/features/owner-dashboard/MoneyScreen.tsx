import { useState } from 'react';
import { View } from 'react-native';
import { AppBar } from '@/shared';
import { Loading, Badge, Btn, Card, Chip, Kpi, List, Note, Row, Screen, T } from '@/design';
import { api, inr, ok, useAction, useQuery, type Schemas } from '@/core/api';

export default function Money() {
  const { act, busy } = useAction();
  /* the year statement stays on screen to read through or show the CA, rather than a toast that goes in seconds */
  const [stmt, setStmt] = useState<Schemas['StatementOut'] | null>(null);
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
      {stmt ? (
        <Card>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <T v="bodyBold">Year statement · FY {stmt.fy}</T>
            <Btn small kind="ghost" label="Close" onPress={() => setStmt(null)} />
          </View>
          <List>
            <Row left="Rent billed" right={inr(stmt.rent_paise)} />
            <Row left="Electricity billed" right={inr(stmt.electricity_paise)} />
            {stmt.deductions_paise > 0 && <Row left="Taken from deposits" right={inr(stmt.deductions_paise)} />}
            <Row left="30% standard deduction on rent" right={inr(stmt.standard_deduction_paise)} last />
          </List>
          {stmt.rows.length > 0 && <>
            <T v="label">By resident</T>
            <List>{stmt.rows.map((r, i) => <Row key={`${r.name}-${r.room}-${i}`} last={i === stmt.rows.length - 1}
              left={<View><T v="bodyBold">{r.name}</T><T v="sm">Room {r.room}</T></View>}
              right={<View style={{ alignItems: 'flex-end' }}><T v="bodyBold">{inr(r.rent_paise)}</T>{r.electricity_paise > 0 && <T v="sm">+ {inr(r.electricity_paise)} electricity</T>}</View>} />)}</List>
          </>}
          <Note tone="soft">{stmt.note}</Note>
        </Card>
      ) : <Btn kind="secondary" label="Year statement for your CA" onPress={() => act(async () => { setStmt(await ok(api.GET('/api/owner/statement'))); })} />}
    </Screen>
  );
}
