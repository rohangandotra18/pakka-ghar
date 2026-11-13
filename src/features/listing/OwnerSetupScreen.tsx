import { useCallback, useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import { Back, Badge, Btn, Chip, Chips, Field, Hero, List, Note, Row, Screen, Steps, T, Toggle, Tick, Otp, C } from '@/design';
import { MapView } from '@/shared';
import { OwnerAgreementTemplate } from '@/features/agreements';
import { OwnerPhotos } from '@/features/photos';
import { api, ApiError, inr, ok, type Schemas, useQuery } from '@/core/api';
import { useStore } from '@/core/session';
import { whereAmI } from '@/core/device';

/* Five steps to send a PG for checking, done in one visit to the building. The bank account, meters and an own
   agreement are not needed to check a PG, so they come after, when they're first needed. */
const STEPS = ['Mobile number', 'Verify identity', 'Your PG', 'Rooms and rent', 'Photos and papers', 'Submit'];
const DONE = 6, PAYOUTS = 7, METERS = 8, AGREEMENT = 9;
/* where the map opens until the owner pins their building */
const CITIES = { chandigarh: { label: 'Chandigarh', lat: 30.7333, lng: 76.7794 }, mohali: { label: 'Mohali', lat: 30.7046, lng: 76.7179 }, panchkula: { label: 'Panchkula', lat: 30.6942, lng: 76.8606 } } as const;
type City = keyof typeof CITIES;
const BLANK = { owner: '', name: '', address: '', area: '', city: 'chandigarh' as string, gender: 'Boys', meals: '3 meals', bank: '', account: '', ifsc: '', kind: 'double', count: '', rent: '', first: '' };
const KIND: Record<string, string> = { single: 'Single', double: 'Double', triple: 'Triple' };

export default function OwnerOnboarding() {
  const { s, signIn, updateMe, toast, refresh, ownerReady } = useStore();
  const me = s.owner?.me;
  const { step } = useLocalSearchParams<{ step?: string }>();
  /* opened from More to change one thing: go straight to it, and come back when done */
  const JUMP: Record<string, number> = { details: 2, rooms: 3, photos: 4, payouts: PAYOUTS, meters: METERS, agreement: AGREEMENT };
  const editing = !!step && step in JUMP;
  const [at, setI] = useState(editing ? JUMP[step!] : me ? (me.verified ? 2 : 1) : 0);
  const i = me ? at : 0;   // a sign-in the server no longer accepts starts again at the phone code
  const [phone, setPhone] = useState('');
  const [challenge, setChallenge] = useState<{ id: string; code: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const prop = useQuery(async () => {
    if (!ownerReady) return null;
    try { return await ok(api.GET('/api/owner/property')); } catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; }
  }, [ownerReady]);
  const p = prop.data ?? null;
  const [edits, setEdits] = useState<Partial<typeof BLANK>>({});
  const f = { ...BLANK, owner: me?.name ?? '', ...(p ? { name: p.name, address: p.address, area: p.area, city: p.city, gender: p.gender, meals: p.meals } : {}), ...edits };
  const set = (k: keyof typeof BLANK) => (v: string) => setEdits(x => ({ ...x, [k]: v }));
  const city = CITIES[(f.city in CITIES ? f.city : 'chandigarh') as City];
  const back = () => (router.canGoBack() ? router.back() : router.replace('/more'));
  const next = () => (editing ? back() : setI(n => Math.min(DONE, n + 1)));
  const run = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try { await fn(); if (done) toast(done); refresh(); return true; } catch (e) { toast(e instanceof ApiError ? e.message : 'Something went wrong. Try again.'); return false; } finally { setBusy(false); }
  };
  const save = (fn: () => Promise<Schemas['PropertyOut']>) => run(async () => { prop.setData(await fn()); });

  const onPick = useCallback((ll: { lat: number; lng: number }) => {
    save(() => ok(api.PUT('/api/owner/property/pin', { body: ll })));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const rooms = p?.rooms ?? [];
  const byKind = Object.entries(rooms.reduce<Record<string, { n: number; beds: number; rent: number }>>((a, r) => {
    const k = (a[r.kind] ??= { n: 0, beds: 0, rent: r.rent_paise });
    k.n += 1; k.beds += r.beds; return a;
  }, {}));
  const paired = rooms.filter(r => r.meter).length;

  return (
    <Screen>
      {i < DONE && <Back label={i === 0 || editing ? 'Back' : 'Previous'} onPress={i === 0 ? undefined : editing ? back : () => setI(i - 1)} />}
      {i > DONE && <Back label="Back" onPress={() => (editing ? back() : setI(DONE))} />}
      {i < DONE && !editing && <Steps i={i} labels={STEPS} />}
      {i === 0 && <>
        <T v="h2">Your mobile number</T>
        <Field label="Mobile number" value={phone} onChangeText={t => { setPhone(t); setChallenge(null); }} keyboard="phone-pad" placeholder="10-digit mobile number" />
        {challenge ? <>
          <Otp code={challenge.code} onChange={code => setChallenge(x => x && { ...x, code })} />
          <Btn label="Verify" disabled={busy} onPress={() => run(async () => {
            const r = await ok(api.POST('/api/auth/otp/verify', { body: { challenge_id: challenge.id, code: challenge.code, device: 'Pakka Ghar app' } }));
            await signIn(null, r.token, r.me);
            /* an owner who already has a PG (signing in on another phone or the website) goes straight to it */
            if (r.me.verified && r.me.memberships.length) { router.replace('/today'); return; }
            setI(r.me.verified ? 2 : 1);
          })} />
        </> : <Btn label="Send code" disabled={busy} onPress={() => run(async () => {
          const r = await ok(api.POST('/api/auth/otp/start', { body: { phone } }));
          setChallenge({ id: r.challenge_id, code: r.dev_code ?? '' });
        })} />}
      </>}
      {i === 1 && <>
        <T v="h2">Verify with Aadhaar</T>
        <T v="sm">Needed to pay rent into your account and to get the Verified badge.</T>
        <Field label="Your full name" value={f.owner} onChangeText={set('owner')} placeholder="As on your Aadhaar" />
        {me?.verified ? <Btn label="Continue" onPress={next} /> : <Btn label="Verify with DigiLocker" disabled={busy || f.owner.trim().length < 2} onPress={async () => {
          const okd = await run(async () => {
            if (f.owner.trim() !== me?.name) updateMe('owner', await ok(api.PATCH('/api/me', { body: { name: f.owner.trim() } })));
            const st = await ok(api.POST('/api/kyc/digilocker/start'));
            updateMe('owner', await ok(api.POST('/api/kyc/digilocker/complete', { body: { txn: st.txn, auth_code: 'consent-given' } })));
          }, 'Verified.');
          if (okd) next();
        }} />}
      </>}
      {i === 2 && <>
        <T v="h2">Your PG</T>
        <Field label="PG name" value={f.name} onChangeText={set('name')} placeholder="What tenants will see" />
        <Field label="Address" value={f.address} onChangeText={set('address')} placeholder="House number, sector" />
        <Field label="Sector or locality" value={f.area} onChangeText={set('area')} placeholder="e.g. Sector 15" />
        <T v="label">City</T>
        <Chips>{(Object.keys(CITIES) as City[]).map(c => <Chip key={c} label={CITIES[c].label} on={f.city === c} onPress={() => set('city')(c)} />)}</Chips>
        <T v="label">For</T>
        <Chips>{['Boys', 'Girls', 'Co-ed'].map(c => <Chip key={c} label={c} on={f.gender === c} onPress={() => set('gender')(c)} />)}</Chips>
        <T v="label">Meals</T>
        <Chips>{['3 meals', '2 meals', 'None'].map(c => <Chip key={c} label={c} on={f.meals === c} onPress={() => set('meals')(c)} />)}</Chips>
        {p && <>
          <T v="label">Pin the building</T>
          <Btn kind="secondary" label="I’m at the building: use my location" disabled={busy} onPress={() => run(async () => {
            const here = await whereAmI();
            if (!here) throw new ApiError(0, 'no_location', 'Couldn’t get your location. Step outside for a moment and try again, or tap the map.');
            prop.setData(await ok(api.PUT('/api/owner/property/pin', { body: here })));
          }, 'Pinned where you’re standing.')} />
          <MapView height={260} center={p.lat != null && p.lng != null ? { lat: p.lat, lng: p.lng } : city} zoom={p.lat != null ? 17 : 13} onPick={onPick} picked={p.lat != null && p.lng != null ? { lat: p.lat, lng: p.lng } : null} />
          <T v="sm">{p.lat != null ? 'Pinned. Tap the map to nudge it onto the entrance.' : 'Or tap the map on your building’s entrance.'}</T>
        </>}
        <Btn label={p ? (editing ? 'Save' : 'Continue') : 'Save and pin the building'} disabled={busy || !f.name.trim() || !f.address.trim() || !f.area.trim() || (!!p && p.lat == null)} onPress={async () => {
          const body = { name: f.name.trim(), address: f.address.trim(), area: f.area.trim(), city: f.city, gender: f.gender, meals: f.meals };
          const okd = await run(async () => {
            if (f.owner.trim() !== me?.name) updateMe('owner', await ok(api.PATCH('/api/me', { body: { name: f.owner.trim() } })));
            if (p) { prop.setData(await ok(api.PATCH('/api/owner/property', { body }))); return; }
            prop.setData(await ok(api.POST('/api/owner/property', { body })));
            updateMe('owner', await ok(api.GET('/api/me')));
          });
          if (okd && p && p.lat != null) next();
        }} />
      </>}
      {i === 3 && <>
        <T v="h2">Rooms and rent</T>
        <T v="sm">Rent is per bed for each room type. You can edit rooms later.</T>
        {byKind.length > 0 && <List>{byKind.map(([k, v], n) => <Row key={k} last={n === byKind.length - 1} left={`${KIND[k]} · ${v.n} room${v.n === 1 ? '' : 's'}`} right={`${v.beds} beds · ${inr(v.rent)}`} />)}</List>}
        <T v="label">{byKind.length ? 'Add more rooms' : 'Add rooms'}</T>
        <Chips>{Object.keys(KIND).map(k => <Chip key={k} label={KIND[k]} on={f.kind === k} onPress={() => set('kind')(k)} />)}</Chips>
        <Field label="How many rooms of this type" value={f.count} onChangeText={set('count')} keyboard="number-pad" placeholder="e.g. 5" />
        <Field label="Rent per bed (₹ a month)" value={f.rent} onChangeText={set('rent')} keyboard="number-pad" placeholder="e.g. 9000" />
        <Field label="First room number" value={f.first} onChangeText={set('first')} keyboard="number-pad" placeholder={String(101 + rooms.length)} />
        <Btn kind="secondary" label="Add these rooms" disabled={busy || !Number(f.count) || !Number(f.rent)} onPress={() => run(async () => {
          prop.setData(await ok(api.POST('/api/owner/rooms', { body: { kind: f.kind, rooms: Number(f.count), rent_paise: Math.round(Number(f.rent) * 100), first_number: Number(f.first) || 101 + rooms.length } })));
          setEdits(x => ({ ...x, count: '', rent: '', first: '' }));
        }, 'Rooms added.')} />
        <List>
          <Row left="Deposit" right={`${p?.deposit_months ?? 1} month`} />
          <Row left="Electricity" right={`By meter, ₹${((p?.tariff_paise ?? 725) / 100).toFixed(2)}/unit`} />
          <Row left="Notice" right={`${p?.notice_months ?? 1} month`} last />
        </List>
        <T v="sm">{rooms.reduce((a, r) => a + r.beds, 0)} beds in all.</T>
        <Btn label={editing ? 'Done' : 'Continue'} disabled={!rooms.length} onPress={next} />
      </>}
      {i === 4 && <>
        <T v="h2">Photos and papers</T>
        <T v="sm">Tenants trust PGs with real photos. Take a few now, at the building: the outside, the rooms, the bathroom, the kitchen. Then add the ownership papers.</T>
        <OwnerPhotos rooms={rooms.map(r => r.number)} />
        <T v="label">Ownership papers</T>
        <T v="sm">We check these once. Only our verification team sees them.</T>
        <List>
          {(p?.documents ?? []).map((d, k, all) => (
            <Row key={d.kind} last={k === all.length - 1} left={d.label} right={d.status === 'uploaded' || d.status === 'accepted'
              ? <Badge label={d.status === 'accepted' ? 'Checked' : 'Uploaded'} tone="ok" />
              : <Chip label={d.kind === 'pg_registration' ? 'Add later' : 'Upload'} onPress={() => d.kind !== 'pg_registration' && save(() => ok(api.POST('/api/owner/documents/{kind}', { params: { path: { kind: d.kind }, query: { file_name: `${d.kind}.pdf` } } })))} />} />
          ))}
        </List>
        <T v="sm">Leasing the building? Upload a lease that allows subletting instead.</T>
        <Btn label={editing ? 'Done' : 'Continue'} onPress={next} />
      </>}
      {i === 5 && <>
        <T v="h2">Send it for checking</T>
        <Note tone="soft"><T v="smBold">No cash, ever.</T><T v="sm" style={{ color: C.ink }}>Pakka Ghar PGs take rent, deposits and electricity only in the app. And it’s all free: no listing fees, no subscription, no payment fees.</T></Note>
        <Toggle on={!!p?.no_cash_pledged} onChange={v => v && !p?.no_cash_pledged && save(() => ok(api.POST('/api/owner/no-cash-pledge')))} label="I won't take cash from residents" />
        <Btn label={p?.status === 'draft' ? 'Send for checking' : 'Continue'} disabled={busy || !p?.no_cash_pledged} onPress={async () => {
          if (p?.status === 'draft') { const sent = await run(async () => prop.setData(await ok(api.POST('/api/owner/property/submit')))); if (!sent) return; }
          next();
        }} />
      </>}
      {i === DONE && <>
        <Hero icon={<Tick />} title={p?.verified ? 'Your PG is live' : 'Sent for checking'} body={p?.verified ? 'Your papers were checked. Changes you made are saved.' : 'The trust team checks your papers within two working days. You can keep editing meanwhile.'} />
        <T v="label">When you need them</T>
        <List>
          <Row left="Bank account for rent" right={p?.payout ? <Badge label="Added" tone="ok" /> : <Chip label="Before your first resident" onPress={() => setI(PAYOUTS)} />} />
          <Row left="Electricity meters" right={paired ? <Badge label={`${paired} paired`} tone="ok" /> : <Chip label="Before the first bill" onPress={() => setI(METERS)} />} />
          <Row left="Your own agreement" right={<Chip label="Optional" onPress={() => setI(AGREEMENT)} />} last />
        </List>
        <Btn label="Open my dashboard" onPress={() => router.replace('/today')} />
      </>}
      {i === PAYOUTS && <>
        <T v="h2">Where rent is paid</T>
        {p?.payout ? <List><Row left="Bank account" right={p.payout} /><Row left="Account check (₹1 test deposit)" right={<Badge label="Name matches" tone="ok" />} last /></List> : <>
          <Field label="Bank" value={f.bank} onChangeText={set('bank')} placeholder="e.g. HDFC Bank" />
          <Field label="Account number" value={f.account} onChangeText={set('account')} keyboard="number-pad" placeholder="As on your passbook or cheque" />
          <Field label="IFSC" value={f.ifsc} onChangeText={set('ifsc')} placeholder="Like SBIN0001234" />
          <Btn kind="secondary" label="Check with a ₹1 test deposit" disabled={busy || !f.bank.trim() || !f.account.trim() || f.ifsc.trim().length !== 11} onPress={() => save(() => ok(api.POST('/api/owner/payout', { body: { bank_name: f.bank, account_number: f.account, ifsc: f.ifsc } })))} />
        </>}
        <T v="sm">Rent reaches you the next working day. Deposits stay in escrow until move-out.</T>
        <Btn label="Done" disabled={!p?.payout} onPress={() => (editing ? back() : setI(DONE))} />
      </>}
      {i === METERS && <>
        <T v="h2">Electricity meters</T>
        <T v="sm">Pair one Wi-Fi meter per room. Readings reach you and the residents automatically, and the bill is added to rent.</T>
        <List>
          {rooms.map((r, k) => <Row key={r.number} last={k === rooms.length - 1} left={`Room ${r.number}`} right={r.meter ? <Badge label={`Paired · ${r.meter}`} tone="ok" /> : <Chip label="Scan meter QR" onPress={() => save(() => ok(api.POST('/api/owner/rooms/{number}/meter', { params: { path: { number: r.number } } })))} />} />)}
        </List>
        <T v="sm">₹{((p?.tariff_paise ?? 725) / 100).toFixed(2)} per unit. The app won’t let you set it above your electricity company’s tariff (₹{((p?.max_tariff_paise ?? 750) / 100).toFixed(2)}).</T>
        <Btn label="Done" onPress={() => (editing ? back() : setI(DONE))} />
      </>}
      {i === AGREEMENT && <>
        <T v="h2">Your agreement</T>
        <T v="sm">Use your own rental agreement or the standard one. Either way it’s signed in the app; no printing, no cash.</T>
        <OwnerAgreementTemplate />
        <Btn label="Done" onPress={() => (editing ? back() : setI(DONE))} />
      </>}
    </Screen>
  );
}
