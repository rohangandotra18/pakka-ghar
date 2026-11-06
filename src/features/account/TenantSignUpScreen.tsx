import { useState } from 'react';
import { router, useLocalSearchParams, type Href } from 'expo-router';
import { Back, Btn, Field, Note, Screen, Steps, T, Otp } from '@/design';
import { api, ApiError, ok } from '@/core/api';
import { useStore } from '@/core/session';

/* Tenants browse without an account. This runs only when they request a bed, bid or ask for a visit, and then
   returns them to what they were doing. Two steps: the phone code, then Aadhaar through DigiLocker. Everything the
   police form needs is asked later, before move-in, and only from someone who has booked. */
const STEPS = ['Mobile number', 'Verify identity'];
const WHY: Record<string, string> = { book: 'To request a bed', offer: 'To bid on a room', visit: 'To schedule a tour', stay: 'To see your stay', signin: 'To sign in' };

export default function TenantOnboarding() {
  const { s, signIn, updateMe, toast, refresh } = useStore();
  const { next, why } = useLocalSearchParams<{ next?: string; why?: string }>();
  const me = s.tenant?.me;
  const [at, setI] = useState(me ? 1 : 0);
  const i = me ? at : 0;   // a sign-in the server no longer accepts starts again at the phone code
  const [phone, setPhone] = useState('');
  const [challenge, setChallenge] = useState<{ id: string; code: string } | null>(null);
  const [name, setName] = useState(me?.name ?? '');
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } catch (e) { toast(e instanceof ApiError ? e.message : 'Something went wrong. Try again.'); } finally { setBusy(false); }
  };
  const done = () => {
    refresh();
    if (next) router.replace(next as Href);
    else if (router.canGoBack()) router.back();
    else router.replace('/find');
  };

  const sendCode = () => run(async () => {
    const r = await ok(api.POST('/api/auth/otp/start', { body: { phone } }));
    setChallenge({ id: r.challenge_id, code: r.dev_code ?? '' });
  });
  const verifyCode = () => run(async () => {
    if (!challenge) return;
    const r = await ok(api.POST('/api/auth/otp/verify', { body: { challenge_id: challenge.id, code: challenge.code, device: 'Pakka Ghar app' } }));
    await signIn(null, r.token, r.me);
    /* one sign-in for everyone: an account that runs a PG opens on the owner dashboard */
    if (r.me.memberships.length) { router.replace('/today'); return; }
    if (r.me.verified) { done(); return; }
    setName(r.me.name ?? '');
    setI(1);
  });
  const verifyId = () => run(async () => {
    if (name.trim() !== (me?.name ?? '')) updateMe('tenant', await ok(api.PATCH('/api/me', { body: { name: name.trim() } })));
    const start = await ok(api.POST('/api/kyc/digilocker/start'));
    /* a real build opens start.redirect_url for consent; DigiLocker calls back with the code and the name, date of
       birth and address from Aadhaar */
    updateMe('tenant', await ok(api.POST('/api/kyc/digilocker/complete', { body: { txn: start.txn, auth_code: 'consent-given' } })));
    toast('You’re verified. Pakka Ghar is free for you.');
    done();
  });

  return (
    <Screen>
      <Back label={i === 0 ? 'Back' : 'Previous'} onPress={i === 0 ? undefined : () => setI(0)} />
      <Steps i={i} labels={STEPS} />
      {i === 0 && <>
        <T v="h2">{why === 'signin' ? 'Sign in' : 'Your mobile number'}</T>
        <Note tone="soft">{why === 'signin' ? 'One account for renting and for running a PG. Browsing never needs one.' : `${WHY[why ?? ''] ?? 'To book'}, verify once. Browsing never needs an account.`}</Note>
        <Field label="Mobile number" value={phone} onChangeText={t => { setPhone(t); setChallenge(null); }} keyboard="phone-pad" placeholder="10-digit mobile number" />
        {challenge ? <>
          <Otp code={challenge.code || '······'} />
          <T v="sm">{challenge.code ? 'Development build: the code is filled in until an SMS provider is connected.' : 'Enter the code we sent on SMS or WhatsApp.'}</T>
          <Btn label="Verify" disabled={busy} onPress={verifyCode} />
        </> : <Btn label="Send code" disabled={busy || phone.replace(/\D/g, '').length < 10} onPress={sendCode} />}
      </>}
      {i === 1 && <>
        <T v="h2">Verify with Aadhaar</T>
        <T v="sm">Owners accept only verified residents. DigiLocker shares a signed copy with your consent; we keep only the last 4 digits.</T>
        <Field label="Full name" value={name} onChangeText={setName} placeholder="As on your Aadhaar" />
        <Btn label="Verify with DigiLocker" disabled={busy || name.trim().length < 2} onPress={verifyId} />
      </>}
    </Screen>
  );
}
