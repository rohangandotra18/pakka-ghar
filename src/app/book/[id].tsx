import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { Back, Btn, Card, Note, Screen, T } from '@/components/ui';
import { TARIFF } from '@/lib/data';
import { pgById, useStore } from '@/lib/store';
import { C, rupees } from '@/lib/theme';

/* Booking: deposit into escrow by UPI, Aadhaar eSign, e-stamp, then the police-verification form. */
export default function Book() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const p = pgById(id);
  const { s, set, toast } = useStore();
  const b = s.booking;
  const rent = s.offer?.accepted && s.offer.pgId === p.id ? s.offer.amount : p.rent;
  const step = (ok: boolean, title: string, sub: string, last?: boolean) => (
    <View style={{ flexDirection: 'row', gap: 10, paddingVertical: 9, borderBottomWidth: last ? 0 : 1, borderBottomColor: C.line }}>
      <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: ok ? C.okBg : 'transparent', borderWidth: ok ? 0 : 1.5, borderColor: C.line, borderStyle: 'dashed', alignItems: 'center', justifyContent: 'center' }}>{ok ? <T v="smBold" style={{ color: C.ok }}>✓</T> : null}</View>
      <View style={{ flex: 1 }}><T v="bodyBold">{title}</T><T v="sm">{sub}</T></View>
    </View>
  );
  const done = b.paid && b.signed && b.stamped;
  return (
    <Screen>
      <Back />
      <T v="h2">Book your bed</T>
      <T v="sm">{p.name} · Room 104 · bed 3 · {rupees(rent)}/month</T>
      <Card style={{ paddingVertical: 4, gap: 0 }}>
        {step(true, 'Identity verified', 'Aadhaar via DigiLocker')}
        {step(b.paid, `Deposit ${rupees(rent)}`, 'Paid by UPI, held in escrow until you move out')}
        {step(b.signed, 'Agreement signed', 'Aadhaar eSign by you and the owner')}
        {step(b.stamped, 'E-stamped', 'Stamp duty goes to the state; Pakka Ghar charges nothing')}
        {step(b.stamped, 'Police verification', 'Form prepared for the owner to submit', true)}
      </Card>
      {!b.paid && <Btn label={`Pay ${rupees(rent)} by UPI`} onPress={() => { set({ booking: { ...b, paid: true } }); toast('Deposit paid and held in escrow.'); }} />}
      {b.paid && !b.signed && <>
        <Card><T v="bodyBold">PG accommodation agreement</T><T v="sm">11 months from 1 Dec 2026 · Rent {rupees(rent)} · Deposit {rupees(rent)} · Notice 1 month · Electricity by meter at ₹{TARIFF}/unit · Rent paid only in the app</T></Card>
        <Btn label="Sign with Aadhaar OTP" onPress={() => { set({ booking: { ...b, signed: true } }); toast('Signed. The owner signs next.'); }} />
      </>}
      {b.signed && !b.stamped && <Btn label="Pay ₹100 stamp duty to the state" onPress={() => { set({ booking: { ...b, stamped: true }, stay: { pgId: p.id, rent, room: '104', since: 'Dec 2026' }, rentPaid: false, rated: false }); toast('E-stamp certificate attached.'); }} />}
      {done && <>
        <Note tone="ok">All done. Move in on 1 December. Your agreement and receipts are under My stay.</Note>
        <Btn label="Go to My stay" onPress={() => router.replace('/stay')} />
      </>}
    </Screen>
  );
}
