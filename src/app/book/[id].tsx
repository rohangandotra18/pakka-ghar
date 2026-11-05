import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { Loading } from '@/components/Loading';
import { Back, Btn, Card, Note, Screen, T } from '@/components/ui';
import { api, idem, inr, ok, type Schemas } from '@/api/client';
import { useAction, useQuery } from '@/api/hooks';
import { C } from '@/lib/theme';

type Booking = Schemas['BookingOut'];
const time = (iso: string) => {
  const d = new Date(iso), t = d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true }).toLowerCase();
  const days = Math.round((new Date(d).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
  return days === 0 ? `${t} today` : days === 1 ? `${t} tomorrow` : `${t} on ${d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`;
};
const day = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' });

/* Booking: the bed is held while the deposit goes into escrow by UPI, then both sides read and sign the agreement (typed name + one-time code),
   e-stamp, and the police-verification form for the owner. */
export default function Book() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { act, busy } = useAction();
  const listing = useQuery(() => ok(api.GET('/api/listings/{slug}', { params: { path: { slug: id } } })), [id]);
  /* the bed the owner held for you when accepting your application (or a booking already under way here) */
  const existing = useQuery(async () => {
    const apps = await ok(api.GET('/api/applications/mine'));
    const won = apps.find(a => a.listing === id && a.status === 'accepted' && a.my_booking_id);
    if (won?.my_booking_id) return ok(api.GET('/api/bookings/{booking_id}', { params: { path: { booking_id: won.my_booking_id } } }));
    const st = (await ok(api.GET('/api/stay'))).stay;
    return st && st.booking.listing === id ? st.booking : null;
  }, [id]);
  const b: Booking | null = existing.data ?? null;

  const p = listing.data;
  if (!p || existing.data === undefined) return <Screen><Back /><Loading error={listing.error ?? existing.error} retry={listing.reload} /></Screen>;
  const rent = b?.rent_paise ?? p.free_bed?.rent_paise ?? p.rent_paise;
  /* an offer raises the rent, never the deposit: it stays at one month of the listed rent */
  const deposit = b?.deposit_paise ?? (p.free_bed?.rent_paise ?? p.rent_paise) * p.deposit_months;
  const paid = !!b?.deposit_paid, signed = !!b?.agreement.tenant_signed, ownerSigned = !!b?.agreement.owner_signed, stamped = !!b?.agreement.stamped;

  const payDeposit = () => act(async () => {
    if (!b) return;
    const pay = await ok(api.POST('/api/bookings/{booking_id}/deposit', { params: { path: { booking_id: b.id } }, ...idem() }));
    /* a release build opens the UPI app here; until a payment partner is connected its confirmation is simulated */
    await ok(api.POST('/api/dev/payments/{payment_id}/capture', { params: { path: { payment_id: pay.id }, query: { method: 'upi' } } }));
    existing.setData(await ok(api.GET('/api/bookings/{booking_id}', { params: { path: { booking_id: b.id } } })));
  }, 'Deposit paid and held in escrow.');

  const step = (done: boolean, title: string, sub: string, last?: boolean) => (
    <View style={{ flexDirection: 'row', gap: 10, paddingVertical: 9, borderBottomWidth: last ? 0 : 1, borderBottomColor: C.line }}>
      <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: done ? C.okBg : 'transparent', borderWidth: done ? 0 : 1.5, borderColor: C.line, borderStyle: 'dashed', alignItems: 'center', justifyContent: 'center' }}>{done ? <T v="smBold" style={{ color: C.ok }}>✓</T> : null}</View>
      <View style={{ flex: 1 }}><T v="bodyBold">{title}</T><T v="sm">{sub}</T></View>
    </View>
  );
  if (!b) return (
    <Screen><Back /><T v="h2">Apply first</T><T v="sm">At {p.name}, the owner picks who stays. Apply, alone or with roommates; once they accept, your bed is held for 24 hours and you pay the deposit here.</T>
      <Btn label="Apply to stay" onPress={() => router.replace(`/apply/${id}`)} /></Screen>
  );
  const moveIn = b?.move_in_on ?? p.move_in_on;
  return (
    <Screen>
      <Back />
      <T v="h2">Book your bed</T>
      <T v="sm">{p.name} · Room {b.room} · bed {b.bed} · {inr(rent)}/month</T>
      {b?.status === 'hold' && b.hold_expires_at && <Note tone="soft">This bed is held for you until {time(b.hold_expires_at)}. Pay the deposit to keep it.</Note>}
      <Card style={{ paddingVertical: 4, gap: 0 }}>
        {step(true, 'Identity verified', 'Aadhaar via DigiLocker')}
        {step(paid, `Deposit ${inr(deposit)}`, 'Paid by UPI, held in escrow until you move out')}
        {step(signed && ownerSigned, 'Agreement signed', signed && !ownerSigned ? 'You signed. Waiting for the owner.' : 'Read every page, then sign with your name and a code')}
        {step(stamped, 'E-stamped', 'Stamp duty goes to the state; Pakka Ghar charges nothing')}
        {step(b?.police === 'verified', 'Police verification', b?.police === 'verified' ? 'Verified by the police' : b?.police === 'submitted' ? 'Submitted by the owner, waiting for the police' : 'Form prepared for the owner to submit', true)}
      </Card>
      {!paid && <Btn label={`Pay ${inr(deposit)} by UPI`} disabled={busy} onPress={payDeposit} />}
      {paid && !signed && b && <>
        <Card><T v="bodyBold">PG accommodation agreement</T><T v="sm">{b.months} months from {day(moveIn)} · Rent {inr(rent)} · Deposit {inr(deposit)} · Notice 1 month · Electricity by meter at ₹{(p.tariff_paise / 100).toFixed(2)}/unit · Rent paid only in the app</T></Card>
        <Btn label="Read and sign the agreement" onPress={() => router.push(`/agreement/${b.id}`)} />
      </>}
      {signed && !ownerSigned && b && <>
        <Note tone="soft">The owner has been asked to sign in their app. You’ll be told here as soon as they do.</Note>
      </>}
      {signed && ownerSigned && !stamped && b && <Btn label="Pay ₹100 stamp duty to the state" disabled={busy} onPress={() => act(async () => existing.setData(await ok(api.POST('/api/bookings/{booking_id}/stamp', { params: { path: { booking_id: b.id } } }))), 'E-stamp certificate attached.')} />}
      {stamped && <>
        <Note tone="ok">All done. Move in on {day(moveIn)}. Your agreement and receipts are under My stay.</Note>
        <Btn label="Go to My stay" onPress={() => router.replace('/stay')} />
      </>}
    </Screen>
  );
}
