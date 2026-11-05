import { useState } from 'react';
import { router, useLocalSearchParams, type Href } from 'expo-router';
import { Back, Badge, Btn, Chip, Chips, Field, Hero, List, Note, Row, Screen, Steps, T } from '@/components/ui';
import { Tick } from '@/components/icons';
import { Otp } from '@/components/Otp';
import { api, ApiError, ok } from '@/api/client';
import { useStore } from '@/lib/store';

/* Tenants browse without an account. This runs only when they book, make an offer or ask for a visit,
   and then returns them to what they were doing. */
const STEPS = ['Mobile number', 'About you', 'Verify identity', 'All set'];
const WHY: Record<string, string> = { book: 'To book a bed', offer: 'To make an offer', visit: 'To book a visit', stay: 'To see your stay' };
const LOOK: Record<string, string> = { 'Girls PG': 'Girls', 'Co-ed': 'Co-ed', 'Boys PG': 'Boys' };

export default function TenantOnboarding() {
  const { s, signIn, updateMe, toast, refresh } = useStore();
  const { next, why, listing } = useLocalSearchParams<{ next?: string; why?: string; listing?: string }>();
  const me = s.tenant?.me;
  /* someone already signed in but not yet verified starts at their first missing step */
  const [i, setI] = useState(me ? (me.verified ? 3 : me.profile?.guardian_name ? 2 : 1) : 0);
  const [phone, setPhone] = useState('');
  const [challenge, setChallenge] = useState<{ id: string; code: string } | null>(null);
  const [f, setF] = useState({
    name: me?.name ?? '', works_at: me?.works_at ?? '', look: Object.keys(LOOK).find(k => LOOK[k] === me?.looking_for) ?? 'Girls PG', move_in: me?.move_in_on ?? '',
    guardian_name: (me?.profile?.guardian_name as string) ?? '', date_of_birth: (me?.profile?.date_of_birth as string) ?? '',
    home_address: (me?.profile?.home_address as string) ?? '', emergency_contact: (me?.profile?.emergency_contact as string) ?? '',
  });
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (v: string) => setF(p => ({ ...p, [k]: v }));
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } catch (e) { toast(e instanceof ApiError ? e.message : 'Something went wrong. Try again.'); } finally { setBusy(false); }
  };
  const advance = () => setI(n => Math.min(STEPS.length - 1, n + 1));

  const sendCode = () => run(async () => {
    const r = await ok(api.POST('/api/auth/otp/start', { body: { phone } }));
    setChallenge({ id: r.challenge_id, code: r.dev_code ?? '' });
  });
  const verifyCode = () => run(async () => {
    if (!challenge) return;
    const r = await ok(api.POST('/api/auth/otp/verify', { body: { challenge_id: challenge.id, code: challenge.code, device: 'Pakka Ghar app' } }));
    await signIn('tenant', r.token, r.me);
    setI(r.me.verified ? 3 : 1);
  });
  const saveProfile = () => run(async () => {
    const r = await ok(api.PATCH('/api/me', { body: { name: f.name, works_at: f.works_at, looking_for: LOOK[f.look], move_in_on: /^\d{4}-\d{2}-\d{2}$/.test(f.move_in) ? f.move_in : undefined,
      guardian_name: f.guardian_name, date_of_birth: f.date_of_birth, home_address: f.home_address, emergency_contact: f.emergency_contact } }));
    updateMe('tenant', r);
    advance();
  });
  const digilocker = () => run(async () => {
    const start = await ok(api.POST('/api/kyc/digilocker/start'));
    /* a real build opens start.redirect_url for consent and DigiLocker calls back with the code */
    const r = await ok(api.POST('/api/kyc/digilocker/complete', { body: { txn: start.txn, auth_code: 'consent-given' } }));
    updateMe('tenant', r);
  });
  const finish = () => run(async () => {
    refresh();
    if (next) router.replace(next as Href);
    else if (router.canGoBack()) router.back();
    else router.replace('/find');
    if (why === 'visit' && listing) {
      await ok(api.POST('/api/visits', { body: { listing } }));
      toast('Visit requested for Saturday 11 am. The owner confirms in the app.');
    }
  });

  return (
    <Screen>
      {i < STEPS.length - 1 && <Back label={i === 0 ? 'Back' : 'Previous'} onPress={i === 0 ? undefined : () => setI(i - 1)} />}
      {i < STEPS.length - 1 && <Steps i={i} labels={STEPS} />}
      {i === 0 && <>
        <T v="h2">Your mobile number</T>
        <Note tone="soft">{`${WHY[why ?? ''] ?? 'To book'}, verify once. Browsing never needs an account.`}</Note>
        <T v="sm">We send a 6-digit code on SMS or WhatsApp.</T>
        <Field label="Mobile number" value={phone} onChangeText={t => { setPhone(t); setChallenge(null); }} keyboard="phone-pad" placeholder="10-digit mobile number" />
        {challenge ? <>
          <Otp code={challenge.code || '······'} />
          <T v="sm">{challenge.code ? 'Code filled in for the demo.' : 'Enter the code we sent.'}</T>
          <Btn label="Verify" disabled={busy} onPress={verifyCode} />
        </> : <Btn label="Send code" disabled={busy} onPress={sendCode} />}
      </>}
      {i === 1 && <>
        <T v="h2">About you</T>
        <Field label="Full name" value={f.name} onChangeText={set('name')} placeholder="As on your Aadhaar" />
        <Field label="Studying or working at" value={f.works_at} onChangeText={set('works_at')} placeholder="College or company" />
        <T v="label">Looking for</T>
        <Chips>{Object.keys(LOOK).map(c => <Chip key={c} label={c} on={f.look === c} onPress={() => set('look')(c)} />)}</Chips>
        <Field label="Move-in (YYYY-MM-DD)" value={f.move_in} onChangeText={set('move_in')} placeholder="Optional" />
        <T v="label">For police verification</T>
        <T v="sm">Chandigarh, Mohali and Panchkula police ask owners to verify every resident. This goes only to the owner you book with.</T>
        <Field label="Father's or guardian's name" value={f.guardian_name} onChangeText={set('guardian_name')} />
        <Field label="Date of birth (YYYY-MM-DD)" value={f.date_of_birth} onChangeText={set('date_of_birth')} placeholder="e.g. 2004-03-12" />
        <Field label="Home address" value={f.home_address} onChangeText={set('home_address')} placeholder="Permanent address" />
        <Field label="Emergency contact" value={f.emergency_contact} onChangeText={set('emergency_contact')} keyboard="phone-pad" placeholder="A parent or guardian's mobile" />
        <Btn label="Continue" disabled={busy || !f.name.trim() || !f.guardian_name.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(f.date_of_birth.trim()) || !f.home_address.trim() || !f.emergency_contact.trim()} onPress={saveProfile} />
      </>}
      {i === 2 && <>
        <T v="h2">Verify your identity</T>
        <T v="sm">Owners accept only verified residents, and police verification needs it. Your ID goes only to the owner you book with.</T>
        <List>
          <Row left="Aadhaar via DigiLocker" right={me?.verified ? <Badge label="Verified" tone="ok" /> : <Badge label="Needed" tone="warn" />} />
          <Row left="Selfie match" right={me?.verified ? <Badge label="Matched" tone="ok" /> : <Badge label="With DigiLocker" />} />
          <Row left="College or employer ID" right={<Badge label="Optional" />} last />
        </List>
        <T v="sm">DigiLocker shares a signed copy with your consent. We keep only the last 4 digits of Aadhaar{me?.aadhaar_masked ? ` (${me.aadhaar_masked.slice(-4)})` : ''}.</T>
        {me?.verified ? <Btn label="Continue" onPress={advance} /> : <Btn label="Verify with DigiLocker" disabled={busy} onPress={digilocker} />}
      </>}
      {i === 3 && <>
        <Hero icon={<Tick />} title="You’re verified" body="Pakka Ghar is free for you. Rent, deposit and electricity are paid only in the app, so every payment is protected and on your record." />
        <Btn label="Continue" disabled={busy} onPress={finish} />
      </>}
    </Screen>
  );
}
