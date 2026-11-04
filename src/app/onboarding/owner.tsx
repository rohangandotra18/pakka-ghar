import { useCallback, useState } from 'react';
import { router } from 'expo-router';
import { Back, Badge, Btn, Chip, Chips, Field, Hero, List, Note, Row, Screen, Steps, T, Toggle } from '@/components/ui';
import { Tick } from '@/components/icons';
import { MapView } from '@/components/MapView';
import { OWNER_PG, useStore } from '@/lib/store';
import { TARIFF } from '@/lib/data';
import { Otp } from '@/components/Otp';

const STEPS = ['Mobile number', 'Verify identity', 'Your property', 'Building on the map', 'Ownership papers', 'Rooms and beds', 'Electricity meters', 'Payouts', 'Submitted'];
const ROOMS = ['101', '102', '103', '104', '201', '202'];
/* where the map opens for the demo owner's address */
const SECTOR_15B = { lat: 30.7543, lng: 76.7713 };

export default function OwnerOnboarding() {
  const { s, set, toast } = useStore();
  const [i, setI] = useState(0);
  const [gender, setGender] = useState('Boys');
  const [meals, setMeals] = useState('3 meals');
  const [noCash, setNoCash] = useState(false);
  const next = () => setI(n => Math.min(STEPS.length - 1, n + 1));
  const paired = Object.keys(s.metersPaired).length;
  const onPick = useCallback((ll: { lat: number; lng: number }) => set(p => ({ pins: { ...p.pins, [OWNER_PG]: ll } })), [set]);
  return (
    <Screen>
      {i < STEPS.length - 1 && <Back label={i === 0 ? 'Back' : 'Previous'} onPress={i === 0 ? undefined : () => setI(i - 1)} />}
      {i < STEPS.length - 1 && <Steps i={i} labels={STEPS} />}
      {i === 0 && <>
        <T v="h2">Your mobile number</T>
        <Field label="Mobile number" value="+91 98140 11150" keyboard="phone-pad" />
        <Otp code="731406" />
        <Btn label="Verify" onPress={next} />
      </>}
      {i === 1 && <>
        <T v="h2">Verify your identity</T>
        <T v="sm">Needed to pay rent into your account and to get the Verified badge.</T>
        <List>
          <Row left="Aadhaar via DigiLocker" right={<Badge label="Verified" tone="ok" />} />
          <Row left="PAN" right={<Badge label="Name matches" tone="ok" />} last />
        </List>
        <Btn label="Continue" onPress={next} />
      </>}
      {i === 2 && <>
        <T v="h2">Your property</T>
        <Field label="PG name" value="Sidhu Boys PG" />
        <Field label="Address" value="House 1150, Sector 15-B, Chandigarh" />
        <T v="label">For</T>
        <Chips>{['Boys', 'Girls', 'Co-ed'].map(c => <Chip key={c} label={c} on={gender === c} onPress={() => setGender(c)} />)}</Chips>
        <T v="label">Meals</T>
        <Chips>{['3 meals', '2 meals', 'None'].map(c => <Chip key={c} label={c} on={meals === c} onPress={() => setMeals(c)} />)}</Chips>
        <Btn label="Continue" onPress={next} />
      </>}
      {i === 3 && <>
        <T v="h2">Pin your building</T>
        <T v="sm">Tap the map on your exact building. Tenants see the listing at this spot, and get directions to it after booking.</T>
        <MapView height={300} center={SECTOR_15B} zoom={16} onPick={onPick} picked={s.pins[OWNER_PG] ?? null} />
        <T v="sm">{s.pins[OWNER_PG] ? 'Pinned. Tap again to move it.' : 'House 1150, Sector 15-B. Tap where the entrance is.'}</T>
        <Btn label="Confirm location" disabled={!s.pins[OWNER_PG]} onPress={next} />
      </>}
      {i === 4 && <>
        <T v="h2">Ownership papers</T>
        <T v="sm">We check these once. Only our verification team sees them.</T>
        <List>
          <Row left="Sale deed or allotment letter" right={<Badge label="Uploaded" tone="ok" />} />
          <Row left="Latest property tax receipt" right={<Badge label="Uploaded" tone="ok" />} />
          <Row left="PG registration (Estate Office)" right={<Badge label="Add later" tone="warn" />} last />
        </List>
        <T v="sm">Leasing the building? Upload a lease that allows subletting instead.</T>
        <Btn label="Continue" onPress={next} />
      </>}
      {i === 5 && <>
        <T v="h2">Rooms and beds</T>
        <T v="sm">Set rent per bed for each room type. You can edit rooms later.</T>
        <List>
          <Row left="Double · 5 rooms" right="10 beds · ₹9,000" />
          <Row left="Triple · 4 rooms" right="12 beds · ₹7,500" />
          <Row left="Single · 2 rooms" right="2 beds · ₹12,000" last />
        </List>
        <List>
          <Row left="Deposit" right="1 month" />
          <Row left="Electricity" right={`By meter, ₹${TARIFF}/unit`} />
          <Row left="Notice" right="1 month" last />
        </List>
        <Btn label="Continue" onPress={next} />
      </>}
      {i === 6 && <>
        <T v="h2">Electricity meters</T>
        <T v="sm">Pair one Wi-Fi meter per room. Readings reach you and the residents automatically, and the bill is added to rent.</T>
        <List>
          {ROOMS.map((r, k) => <Row key={r} last={k === ROOMS.length - 1} left={`Room ${r}`} right={s.metersPaired[r] ? <Badge label="Paired · Qube One" tone="ok" /> : <Chip label="Scan meter QR" onPress={() => { set(p => ({ metersPaired: { ...p.metersPaired, [r]: true } })); toast(`Room ${r} meter paired.`); }} />} />)}
        </List>
        <T v="sm">₹{TARIFF} per unit. The app won’t let you set it above your DISCOM tariff.</T>
        <Btn label={paired ? 'Continue' : 'Skip for now'} onPress={next} />
      </>}
      {i === 7 && <>
        <T v="h2">Where rent is paid</T>
        <Field label="Bank account" value="XXXX XXXX 4417 · HDFC Bank" />
        <List><Row left="Account check (₹1 test deposit)" right={<Badge label="Name matches" tone="ok" />} last /></List>
        <T v="sm">Rent reaches you the next working day. Deposits stay in escrow until move-out.</T>
        <Note tone="soft"><T v="smBold">No cash, ever.</T><T v="sm" style={{ color: '#111714' }}>Pakka Ghar PGs take rent, deposits and electricity only in the app. And it’s all free: no listing fees, no subscription, no payment fees.</T></Note>
        <Toggle on={noCash} onChange={setNoCash} label="I won't take cash from residents" />
        <Btn label="Continue" disabled={!noCash} onPress={next} />
      </>}
      {i === 8 && <>
        <Hero icon={<Tick />} title="Submitted for verification" body="Our team checks your papers within two working days. Meanwhile, set up your bed board and invite current residents to AutoPay." />
        <Btn label="Open my dashboard" onPress={() => { set({ ownerReady: true, role: 'owner' }); router.replace('/today'); }} />
      </>}
    </Screen>
  );
}
