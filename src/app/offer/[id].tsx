import { router, useLocalSearchParams } from 'expo-router';
import { Pressable, View } from 'react-native';
import { Tick } from '@/components/icons';
import { Back, Btn, Chip, Chips, Hero, List, Note, Row, Screen, T } from '@/components/ui';
import { pgById, useStore } from '@/lib/store';
import { C, R, rupees } from '@/lib/theme';

/* A sealed offer on a scarce bed: capped at 15% over the listed rent, deposit unchanged, nothing charged unless accepted. */
export default function MakeOffer() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const p = pgById(id);
  const { s, set, toast } = useStore();
  const o = s.offer ?? { pgId: p.id, amount: p.rent, months: 11, placed: false, accepted: false };
  const cap = Math.round((p.rent * 1.15) / 50) * 50;
  const upd = (u: Partial<typeof o>) => set({ offer: { ...o, ...u } });
  const step = (d: number) => upd({ amount: Math.min(cap, Math.max(p.rent, o.amount + d)) });

  if (o.accepted) return (
    <Screen>
      <Back />
      <Hero icon={<Tick />} title="Offer accepted" body={`${p.name} accepted ${rupees(o.amount)} a month for ${o.months} months. Pay the deposit within 24 hours to hold the bed.`} />
      <Btn label="Pay deposit and sign" onPress={() => { set({ booking: { paid: false, signed: false, stamped: false } }); router.push(`/book/${p.id}`); }} />
    </Screen>
  );
  if (o.placed) {
    const share = (o.amount - p.rent) / (cap - p.rent || 1);
    const rank = share >= 0.75 ? 1 : share >= 0.45 ? 2 : 3;
    const top = Math.round((p.rent * 1.133) / 100) * 100;
    return (
      <Screen>
        <Back />
        <T v="h2">Your offer</T>
        <List>
          <Row left="Rent offered" right={`${rupees(o.amount)}/month`} />
          <Row left="Stay" right={`${o.months} months`} />
          <Row left="Move-in" right="1 December" />
          <Row left="Offers so far" right={`9 · ${rupees(p.rent)}–${rupees(top)}`} />
          <Row left="Your standing" right={`Top ${rank} likely`} last />
        </List>
        <T v="sm">Owners weigh rent, stay length and your verified rental history. You’ll hear by Friday 6 pm. Nothing is charged unless your offer is accepted.</T>
        <Btn label="Simulate: owner accepts" onPress={() => upd({ accepted: true })} />
        <Btn kind="secondary" label="Withdraw offer" onPress={() => upd({ placed: false })} />
      </Screen>
    );
  }
  const pct = (o.amount - p.rent) / (cap - p.rent || 1);
  return (
    <Screen>
      <Back />
      <T v="h2">Make an offer</T>
      <T v="sm">{p.name} · double sharing · listed at {rupees(p.rent)}</T>
      <View style={{ alignItems: 'center', gap: 10, paddingVertical: 6 }}>
        <T v="h1" style={{ fontSize: 36, lineHeight: 42 }}>{rupees(o.amount)}<T v="sm"> /month</T></T>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, alignSelf: 'stretch' }}>
          <StepBtn label="−" onPress={() => step(-100)} />
          <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: C.line }}><View style={{ width: `${Math.round(pct * 100)}%`, height: 6, borderRadius: 3, backgroundColor: C.accent }} /></View>
          <StepBtn label="+" onPress={() => step(100)} />
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignSelf: 'stretch' }}><T v="sm">Listed {rupees(p.rent)}</T><T v="sm">Cap {rupees(cap)} (15%)</T></View>
      </View>
      <T v="label">Stay length</T>
      <Chips>{[6, 9, 11].map(m => <Chip key={m} label={`${m} months`} on={o.months === m} onPress={() => upd({ months: m })} />)}</Chips>
      <Note tone="soft">Longer stays and a good rental history count as much as rent. Offers can’t go more than 15% over the listed rent, and the deposit stays at one month.</Note>
      <Btn label="Place offer" onPress={() => { upd({ placed: true }); toast("Offer placed. Nothing is charged unless it's accepted."); }} />
    </Screen>
  );
}
function StepBtn({ label, onPress }: { label: string; onPress: () => void }) {
  return <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label === '+' ? 'Raise offer by ₹100' : 'Lower offer by ₹100'} style={{ width: 44, height: 44, borderRadius: R.md, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center' }}><T v="h3">{label}</T></Pressable>;
}
