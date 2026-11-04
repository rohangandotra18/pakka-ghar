import { useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { Back, Badge, Btn, List, Row, Screen, T } from '@/components/ui';
import { RESIDENTS } from '@/lib/data';
import { useStore } from '@/lib/store';
import { rupees } from '@/lib/theme';

export default function Resident() {
  const { name } = useLocalSearchParams<{ name: string }>();
  const r = RESIDENTS.find(x => x.name === name) ?? RESIDENTS[0];
  const { s, set, toast } = useStore();
  const pv = s.police[r.name] ?? r.police;
  return (
    <Screen>
      <Back />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><T v="h2">{r.name}</T><Badge label={`Room ${r.room}`} /></View>
      <List>
        <Row left="Identity" right={<Badge label="Aadhaar verified" tone="ok" />} />
        <Row left="Police verification" right={<Badge label={pv} tone={pv === 'Verified' ? 'ok' : pv === 'Submitted' ? 'warn' : 'crit'} />} />
        <Row left="Agreement" right="Signed · e-stamped" />
        <Row left="Rent" right={`${rupees(r.rent)} · ${r.autopay ? 'AutoPay' : 'UPI'}`} />
        <Row left="Deposit" right={`${rupees(r.rent)} in escrow`} />
        <Row left="Since" right={r.since} last />
      </List>
      {pv !== 'Verified' && <Btn label={pv === 'Not started' ? 'Submit police verification' : 'Mark verified'} onPress={() => { const next = pv === 'Not started' ? 'Submitted' : 'Verified'; set(p => ({ police: { ...p.police, [r.name]: next } })); toast(`Police verification: ${next.toLowerCase()}.`); }} />}
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Btn kind="secondary" style={{ flex: 1 }} label="Agreement" onPress={() => toast('Agreement opened: signed by both, e-stamp certificate attached.')} />
        <Btn kind="secondary" style={{ flex: 1 }} label="End stay and rate" onPress={() => toast(`Move-out started: deposit settlement and rating sent to ${r.name.split(' ')[0]}.`)} />
      </View>
    </Screen>
  );
}
