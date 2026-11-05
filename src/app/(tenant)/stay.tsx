import { router } from 'expo-router';
import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Loading } from '@/components/Loading';
import { SignupPrompt } from '@/components/SignupPrompt';
import { TenantPlans } from '@/components/TenantPlans';
import { Bars } from '@/components/icons';
import { Badge, Btn, Card, Chip, List, Note, Row, Screen, T, Toggle } from '@/components/ui';
import { api, idem, inr, ok } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { useStore } from '@/lib/store';

const dayMonth = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' });
const ago = (iso?: string | null) => {
  if (!iso) return 'not synced yet';
  const m = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 60 ? `synced ${m} min ago` : m < 1440 ? `synced ${Math.round(m / 60)} h ago` : `synced ${Math.round(m / 1440)} days ago`;
};

export default function Stay() {
  const { tenantReady } = useStore();
  const { act, busy } = useAction();
  const q = useQuery(() => (tenantReady ? ok(api.GET('/api/stay')) : Promise.resolve({ stay: null })), [tenantReady]);
  if (!tenantReady) return <SignupPrompt title="Your stay lives here" body="Once you book, your rent, electricity reading, agreement and receipts show up here. Browsing doesn’t need an account." />;
  if (!q.data) return <Screen><AppBar /><Loading error={q.error} retry={q.reload} /></Screen>;
  const st = q.data.stay;
  if (!st) return (
    <Screen>
      <AppBar />
      <T v="h2">No stay yet</T>
      <TenantPlans />
      <Card>
        <T v="sm">Once an owner accepts you and you pay the deposit, this is where you pay rent, see your room’s electricity reading, and keep your agreement and receipts.</T>
        <Btn label="Find a PG" onPress={() => router.replace('/find')} />
      </Card>
    </Screen>
  );
  const b = st.booking, bill = st.bill, moved = st.moved_in;
  const lines = bill?.lines ?? [];
  const rent = lines.find(l => l.kind === 'rent')?.amount_paise ?? b.rent_paise;
  const power = lines.find(l => l.kind === 'electricity');
  const total = bill ? bill.total_paise : b.rent_paise;
  const paid = bill?.status === 'paid';
  const month = new Date(bill?.period ?? b.move_in_on).toLocaleString('en-IN', { month: 'long' });
  const payNow = () => act(async () => {
    const pay = await ok(api.POST('/api/stay/pay', idem()));
    /* a release build opens the UPI app; in development the payment partner's confirmation comes from the dev stand-in */
    await ok(api.POST('/api/dev/payments/{payment_id}/capture', { params: { path: { payment_id: pay.id }, query: { method: 'upi' } } }));
  }, 'Paid. Receipt saved.');
  return (
    <Screen>
      <AppBar />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><T v="h2" style={{ flex: 1 }}>{b.name}</T><Badge label={`Room ${b.room}`} /></View>
      <T v="sm">{moved ? `Since ${st.since} · agreement for ${b.months} months` : `Moving in on ${dayMonth(b.move_in_on)} · agreement for ${b.months} months`}</T>
      {st.leaves_on && <Note tone="soft">Notice given. You leave on {dayMonth(st.leaves_on)}; the owner has been told.</Note>}
      {!moved && <Note tone="ok">Booked. Your deposit is in escrow{b.agreement.stamped ? ' and the agreement is signed and e-stamped' : ''}. First rent is due by {st.first_due_on ? dayMonth(st.first_due_on) : 'the 5th'}.</Note>}
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">{month}</T>{!moved ? <Badge label={`Due ${st.first_due_on ? dayMonth(st.first_due_on) : '5th'}`} tone="warn" /> : paid ? <Badge label="Paid" tone="ok" /> : <Badge label={`Due ${dayMonth(bill!.due_on)}`} tone="warn" />}</View>
        <Row left="Rent" right={inr(rent)} />
        <Row left={power ? `Electricity · ${power.quantity} units` : moved ? 'Electricity · added when the owner sends bills' : 'Electricity · billed from your first month'} right={inr(power?.amount_paise ?? 0)} />
        <Row left="Total" right={<T v="price">{inr(total)}</T>} last />
        {moved && (paid ? <T v="sm">Paid in the app. Receipt with the owner’s PAN is saved for your HRA claim.</T> : <Btn label={`Pay ${inr(total - (bill?.paid_paise ?? 0))} by UPI`} disabled={busy} onPress={payNow} />)}
        <Toggle on={st.autopay} onChange={v => act(() => ok(api.PUT('/api/stay/autopay', { body: { on: v } })), v ? 'UPI AutoPay set for the 1st of each month.' : 'AutoPay turned off.')} label="UPI AutoPay on the 1st of each month" />
      </Card>
      {st.meter && <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">Electricity</T><T v="sm">{st.meter.model} · {ago(st.meter.synced_at)}</T></View>
        {st.meter.daily_kwh.length > 1 && <Bars data={st.meter.daily_kwh} />}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="sm">Last {st.meter.daily_kwh.length} days · {Math.round(st.meter.units_14d)} units (your share)</T><T v="sm">₹{(st.meter.tariff_paise / 100).toFixed(2)}/unit</T></View>
        <T v="sm">You and the owner see the same reading. The bill is added to rent at month end.</T>
      </Card>}
      <List>
        <Row left="Agreement" right={<Chip label={b.agreement.stamped ? 'Signed · read' : b.agreement.tenant_signed ? 'Waiting for owner · read' : 'Read and sign'} onPress={() => router.push(`/agreement/${b.id}`)} />} />
        <Row left="Deposit" right={`${inr(b.deposit_paise)} in escrow`} />
        <Row left="Police verification" right={b.police === 'verified' ? <Badge label="Verified" tone="ok" /> : <Badge label={b.police === 'submitted' ? 'Submitted' : 'With the owner'} tone="warn" />} />
        <Row left="Receipts" right={`${st.receipts} saved`} last />
      </List>
      {moved && <View style={{ flexDirection: 'row', gap: 8 }}>
        {!st.leaves_on && <Btn kind="secondary" style={{ flex: 1 }} label="Give notice" disabled={busy} onPress={() => act(() => ok(api.POST('/api/stay/notice')), r => r.stay?.leaves_on ? `Notice recorded: you leave on ${dayMonth(r.stay.leaves_on)}. The owner is told.` : undefined)} />}
        <Btn kind="secondary" style={{ flex: 1 }} label="End stay and rate" onPress={() => router.push('/rate')} />
      </View>}
    </Screen>
  );
}
