import { router, type Href } from 'expo-router';
import { View } from 'react-native';
import { AppBar } from '@/components/AppBar';
import { Chip, Kpi, List, Row, Screen, T } from '@/components/ui';
import { OFFERS, RESIDENTS } from '@/lib/data';
import { useStore } from '@/lib/store';

export default function Today() {
  const { s } = useStore();
  const unpaid = RESIDENTS.filter(r => !r.paid && !s.paidByApp[r.name]).length;
  const open = s.ownerRequests.filter(r => r.status !== 'Fixed').length;
  const todo: [string, string, Href][] = [];
  if (s.offersOpen) todo.push([`${OFFERS.length} offers on Room 104, bed 3`, 'Review', '/offers']);
  if (open) todo.push([`${open} maintenance requests`, 'Open', '/tickets']);
  const nikhil = s.police['Nikhil Rana'] ?? 'Not started';
  if (nikhil !== 'Verified') todo.push([`Nikhil Rana: police verification ${nikhil === 'Submitted' ? 'submitted, awaiting police' : 'not started'}`, nikhil === 'Submitted' ? 'View' : 'Fix', '/resident/Nikhil Rana']);
  todo.push(['November electricity bills are ready', 'Send', '/money']);
  return (
    <Screen>
      <AppBar />
      <T v="h2">Good morning, Jatinder</T>
      <View style={{ flexDirection: 'row', gap: 8 }}><Kpi n="21/24" t="Beds filled" /><Kpi n={String(unpaid)} t="Rent unpaid" alert={unpaid > 0} /></View>
      <View style={{ flexDirection: 'row', gap: 8 }}><Kpi n={String(s.offersOpen ? OFFERS.length : 0)} t="Offers on free beds" /><Kpi n={String(open)} t="Open requests" alert={open > 0} /></View>
      <T v="label">To do</T>
      <List>{todo.map(([t, b, href], i) => <Row key={t} last={i === todo.length - 1} left={t} right={<Chip label={b} onPress={() => router.push(href)} />} />)}</List>
    </Screen>
  );
}
