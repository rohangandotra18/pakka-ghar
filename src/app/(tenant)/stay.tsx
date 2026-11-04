import { router } from 'expo-router';
import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { SignupPrompt } from '@/components/SignupPrompt';
import { Bars } from '@/components/icons';
import { Badge, Btn, Card, List, Note, Row, Screen, T, Toggle } from '@/components/ui';
import { DAILY_KWH, TARIFF } from '@/lib/data';
import { pgById, SAMPLE_REQUEST, SAMPLE_STAY, useStore } from '@/lib/store';
import { rupees } from '@/lib/theme';

export default function Stay() {
  const { s, set, toast } = useStore();
  if (!s.tenantReady) return <SignupPrompt title="Your stay lives here" body="Once you book, your rent, electricity reading, agreement and receipts show up here. Browsing doesn’t need an account." next="/stay" />;
  if (!s.stay) return (
    <Screen>
      <AppBar />
      <T v="h2">No stay yet</T>
      <Card>
        <T v="sm">When you book a bed, this is where you pay rent, see your room’s electricity reading, and keep your agreement and receipts.</T>
        <Btn label="Find a PG" onPress={() => router.replace('/find')} />
        <Btn kind="ghost" label="Demo: see a sample stay" onPress={() => { set(p => ({ stay: SAMPLE_STAY, myRequests: p.myRequests.length ? p.myRequests : [SAMPLE_REQUEST] })); toast('Sample stay loaded.'); }} />
      </Card>
    </Screen>
  );
  const pg = pgById(s.stay.pgId), rent = s.stay.rent;
  const moved = s.stay.since !== 'Dec 2026';
  const kwh = moved ? 86 : 0, power = Math.round(kwh * TARIFF), total = rent + power;
  return (
    <Screen>
      <AppBar />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}><T v="h2" style={{ flex: 1 }}>{pg.name}</T><Badge label={`Room ${s.stay.room}`} /></View>
      <T v="sm">{moved ? `Since ${s.stay.since} · agreement for 11 months` : 'Moving in on 1 December · agreement for 11 months'}</T>
      {!moved && <Note tone="ok">Booked. Your deposit is in escrow and the agreement is signed and e-stamped. First rent is due on 1 December.</Note>}
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">{moved ? 'November' : 'December'}</T>{s.rentPaid ? <Badge label="Paid" tone="ok" /> : <Badge label={moved ? 'Due 5 Nov' : 'Due 5 Dec'} tone="warn" />}</View>
        <Row left="Rent" right={rupees(rent)} />
        <Row left={moved ? `Electricity · ${kwh} units` : 'Electricity · billed from your first month'} right={rupees(power)} />
        <Row left="Total" right={<T v="price">{rupees(total)}</T>} last />
        {s.rentPaid ? <T v="sm">Paid by UPI. Receipt with the owner’s PAN is saved for your HRA claim.</T> : <Btn label={`Pay ${rupees(total)} by UPI`} onPress={() => { set({ rentPaid: true }); toast('Paid. Receipt saved.'); }} />}
        <Toggle on={s.autopay} onChange={v => { set({ autopay: v }); toast(v ? 'UPI AutoPay set for the 1st of each month.' : 'AutoPay turned off.'); }} label="UPI AutoPay on the 1st of each month" />
      </Card>
      {moved && <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="bodyBold">Electricity</T><T v="sm">Qube One · synced 10 min ago</T></View>
        <Bars data={DAILY_KWH} />
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><T v="sm">Last 14 days · 38 units</T><T v="sm">₹{TARIFF}/unit</T></View>
        <T v="sm">You and the owner see the same reading. The bill is added to rent at month end.</T>
      </Card>}
      <List>
        <Row left="Agreement" right="Signed · e-stamped" />
        <Row left="Deposit" right={`${rupees(rent)} in escrow`} />
        <Row left="Police verification" right={moved ? <Badge label="Verified" tone="ok" /> : <Badge label="With the owner" tone="warn" />} />
        <Row left="Receipts" right={moved ? '3 saved' : 'Deposit receipt saved'} last />
      </List>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Btn kind="secondary" style={{ flex: 1 }} label="Give notice" onPress={() => toast('Notice recorded: you leave on 4 January. The owner is told.')} />
        <Btn kind="secondary" style={{ flex: 1 }} label="End stay and rate" onPress={() => router.push('/rate')} />
      </View>
    </Screen>
  );
}
