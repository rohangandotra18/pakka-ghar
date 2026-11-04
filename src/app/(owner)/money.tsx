import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Badge, Btn, Chip, Kpi, List, Note, Row, Screen, T } from '@/components/ui';
import { RESIDENTS, TARIFF } from '@/lib/data';
import { useStore } from '@/lib/store';
import { rupees } from '@/lib/theme';

export default function Money() {
  const { s, toast } = useStore();
  const due = (r: (typeof RESIDENTS)[number]) => r.rent + Math.round(r.kwh * TARIFF);
  const total = RESIDENTS.reduce((a, r) => a + due(r), 0);
  const got = RESIDENTS.filter(r => r.paid || s.paidByApp[r.name]).reduce((a, r) => a + due(r), 0);
  return (
    <Screen>
      <AppBar />
      <T v="h2">November</T>
      <View style={{ flexDirection: 'row', gap: 8 }}><Kpi n={rupees(got)} t="Collected in the app" /><Kpi n={rupees(total)} t="Due · rent + electricity" /></View>
      <T v="label">Residents</T>
      <List>
        {RESIDENTS.map((r, i) => (
          <Row key={r.name} last={i === RESIDENTS.length - 1}
            left={<View><T v="bodyBold">{r.name}</T><T v="sm">Room {r.room} · {r.kwh} units · {r.autopay ? 'AutoPay' : 'UPI'}</T></View>}
            right={r.paid || s.paidByApp[r.name] ? <Badge label="Paid" tone="ok" /> : <Chip label="Remind" onPress={() => toast(`Reminder sent to ${r.name.split(' ')[0]} in the app and on WhatsApp.`)} />} />
        ))}
      </List>
      <Note tone="soft">Rent counts as paid only when it arrives through the app. Cash can’t be recorded.</Note>
      <T v="label">Electricity by room</T>
      <List>
        {[['101', 198], ['102', 64], ['103', 119]].map(([room, u], i) => <Row key={room} last={i === 2} left={`Room ${room} · ${u} units`} right={rupees(Number(u) * TARIFF)} />)}
      </List>
      <T v="sm">Read from Qube meters on 31 Oct at ₹{TARIFF}/unit. Residents saw the same readings.</T>
      <List>
        <Row left="Deposits in escrow" right={rupees(171000)} />
        <Row left="Next payout" right="Tomorrow · HDFC ••4417" last />
      </List>
      <Btn kind="secondary" label="Download year statement for your CA" onPress={() => toast('FY 2026–27 statement prepared: rent per resident, 30% standard deduction applied.')} />
    </Screen>
  );
}
