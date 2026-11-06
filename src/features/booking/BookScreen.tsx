import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';
import { useState } from 'react';
import { Loading, Back, Btn, Card, Field, Note, Screen, T, C } from '@/design';
import { api, idem, inr, ok, type Schemas, useAction, useQuery } from '@/core/api';

type Booking = Schemas['BookingOut'];
const time = (iso: string) => {
  const d = new Date(iso), t = d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true }).toLowerCase();
  const days = Math.round((new Date(d).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
  return days === 0 ? `${t} today` : days === 1 ? `${t} tomorrow` : `${t} on ${d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`;
};
const day = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' });

/* Confirm and pay: the owner signed when they accepted. The resident reads and signs the agreement with one code,
   then pays the deposit into escrow by UPI; paying confirms the booking and e-stamps the agreement. Before move-in,
   the few details the police form still needs are asked here. */
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
  const [police, setPolice] = useState<Record<string, string>>({});

  const p = listing.data;
  if (!p || existing.data === undefined) return <Screen><Back /><Loading error={listing.error ?? existing.error} retry={listing.reload} /></Screen>;
  const rent = b?.rent_paise ?? p.free_bed?.rent_paise ?? p.rent_paise;
  /* an offer raises the rent, never the deposit: it stays at one month of the listed rent */
  const deposit = b?.deposit_paise ?? (p.free_bed?.rent_paise ?? p.rent_paise) * p.deposit_months;
  const paid = !!b?.deposit_paid, signed = !!b?.agreement.tenant_signed, ownerSigned = !!b?.agreement.owner_signed;

  const payDeposit = () => act(async () => {
    if (!b) return;
    const pay = await ok(api.POST('/api/bookings/{booking_id}/deposit', { params: { path: { booking_id: b.id } }, ...idem() }));
    /* a release build opens the UPI app here; until a payment partner is connected its confirmation is simulated */
    await ok(api.POST('/api/dev/payments/{payment_id}/capture', { params: { path: { payment_id: pay.id }, query: { method: 'upi' } } }));
    existing.setData(await ok(api.GET('/api/bookings/{booking_id}', { params: { path: { booking_id: b.id } } })));
  }, 'Booked. Your deposit is in escrow and the agreement is e-stamped.');

  /* the police form's missing fields, as the profile fields that fill them */
  const POLICE: Record<string, { key: string; label: string; placeholder?: string; keyboard?: 'phone-pad' }> = {
    father_or_guardian_name: { key: 'guardian_name', label: 'Father’s or guardian’s name' },
    date_of_birth: { key: 'date_of_birth', label: 'Date of birth (YYYY-MM-DD)', placeholder: 'e.g. 2004-03-12' },
    permanent_address: { key: 'home_address', label: 'Home address', placeholder: 'Permanent address' },
    previous_address: { key: 'home_address', label: 'Home address', placeholder: 'Permanent address' },
    emergency_contact: { key: 'emergency_contact', label: 'Emergency contact', placeholder: 'A parent or guardian’s mobile', keyboard: 'phone-pad' },
    workplace_or_college: { key: 'works_at', label: 'College or workplace' },
    occupation: { key: 'works_at', label: 'College or workplace' },
  };
  const asks = [...new Map((b?.police_missing ?? []).filter(m => POLICE[m]).map(m => [POLICE[m].key, POLICE[m]])).values()];
  const savePolice = () => act(async () => {
    if (!b) return;
    await ok(api.PATCH('/api/me', { body: police }));
    existing.setData(await ok(api.GET('/api/bookings/{booking_id}', { params: { path: { booking_id: b.id } } })));
  }, 'Saved. The owner can submit your police verification now.');

  const step = (done: boolean, title: string, sub: string, last?: boolean) => (
    <View style={{ flexDirection: 'row', gap: 10, paddingVertical: 9, borderBottomWidth: last ? 0 : 1, borderBottomColor: C.line }}>
      <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: done ? C.okBg : 'transparent', borderWidth: done ? 0 : 1.5, borderColor: C.line, borderStyle: 'dashed', alignItems: 'center', justifyContent: 'center' }}>{done ? <T v="smBold" style={{ color: C.ok }}>✓</T> : null}</View>
      <View style={{ flex: 1 }}><T v="bodyBold">{title}</T><T v="sm">{sub}</T></View>
    </View>
  );
  if (!b) return (
    <Screen><Back /><T v="h2">Request a bed first</T><T v="sm">At {p.name}, the owner picks who stays. Send a request, alone or with roommates. When they accept, your bed is held for 24 hours for you to sign and pay.</T>
      <Btn label="Request a bed" onPress={() => router.replace(`/apply/${id}`)} /></Screen>
  );
  const moveIn = b.move_in_on ?? p.move_in_on;
  const booked = b.status === 'confirmed' || b.status === 'active';
  return (
    <Screen>
      <Back />
      <T v="h2">{booked ? 'You’re booked' : 'Confirm and pay'}</T>
      <T v="sm">{p.name} · Room {b.room} · bed {b.bed}</T>
      {b.status === 'hold' && b.hold_expires_at && <Note tone="soft">Held for you until {time(b.hold_expires_at)}.</Note>}
      <Card>
        <T v="bodyBold">What you’re agreeing to</T>
        <T v="sm">{b.months} months from {day(moveIn)}{'\n'}Rent {inr(rent)} a month, paid in the app{'\n'}Deposit {inr(deposit)}, held in escrow until you leave{'\n'}One month’s notice · electricity by meter at ₹{(p.tariff_paise / 100).toFixed(2)} a unit{'\n'}No cash, ever</T>
      </Card>
      <Card style={{ paddingVertical: 4, gap: 0 }}>
        {step(ownerSigned, 'Owner signed', 'When they accepted you')}
        {step(signed, 'You sign', 'Read every page, then confirm with a code')}
        {step(paid, `Deposit ${inr(deposit)}`, 'One UPI payment; the agreement is e-stamped when it’s paid')}
        {step(b.police === 'verified' || b.police === 'submitted' || (booked && asks.length === 0), 'Police verification', b.police === 'verified' ? 'Verified by the police' : b.police === 'submitted' ? 'Submitted by the owner' : booked && asks.length ? 'A few details needed, below' : 'Filled in from your Aadhaar; the owner submits it', true)}
      </Card>
      {!signed && <Btn label="Read and sign the agreement" onPress={() => router.push(`/agreement/${b.id}`)} />}
      {signed && !paid && b.status === 'hold' && <Btn label={`Pay ${inr(deposit)} by UPI`} disabled={busy} onPress={payDeposit} />}
      {booked && asks.length > 0 && <Card>
        <T v="bodyBold">For your police verification</T>
        <T v="sm">Police in the Tricity ask owners to verify every resident. These go only to {p.name}.</T>
        {asks.map(a => <Field key={a.key} label={a.label} placeholder={a.placeholder} keyboard={a.keyboard} value={police[a.key] ?? ''} onChangeText={t => setPolice(x => ({ ...x, [a.key]: t }))} />)}
        <Btn label="Save" disabled={busy || asks.some(a => !(police[a.key] ?? '').trim())} onPress={savePolice} />
      </Card>}
      {booked && <>
        <Note tone="ok">Move in on {day(moveIn)}. Your agreement and receipts are under My stay.</Note>
        <Btn kind="secondary" label="Go to My stay" onPress={() => router.replace('/stay')} />
      </>}
    </Screen>
  );
}
