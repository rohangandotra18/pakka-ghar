import { useState } from 'react';
import { router, useLocalSearchParams, type Href } from 'expo-router';
import { Back, Badge, Btn, Chip, Chips, Field, Hero, List, Note, Row, Screen, Steps, T } from '@/components/ui';
import { Tick } from '@/components/icons';
import { Otp } from '@/components/Otp';
import { useStore } from '@/lib/store';

/* Tenants browse without an account. This runs only when they book, make an offer or ask for a visit,
   and then returns them to what they were doing. */
const STEPS = ['Mobile number', 'About you', 'Verify identity', 'All set'];
const WHY: Record<string, string> = { book: 'To book a bed', offer: 'To make an offer', visit: 'To book a visit', stay: 'To see your stay' };

export default function TenantOnboarding() {
  const { set } = useStore();
  const { next, why } = useLocalSearchParams<{ next?: string; why?: string }>();
  const [i, setI] = useState(0);
  const [look, setLook] = useState('Girls PG');
  const advance = () => setI(n => Math.min(STEPS.length - 1, n + 1));
  return (
    <Screen>
      {i < STEPS.length - 1 && <Back label={i === 0 ? 'Back' : 'Previous'} onPress={i === 0 ? undefined : () => setI(i - 1)} />}
      {i < STEPS.length - 1 && <Steps i={i} labels={STEPS} />}
      {i === 0 && <>
        <T v="h2">Your mobile number</T>
        <Note tone="soft">{`${WHY[why ?? ''] ?? 'To book'}, verify once. Browsing never needs an account.`}</Note>
        <T v="sm">We send a 6-digit code on SMS or WhatsApp.</T>
        <Field label="Mobile number" value="+91 98765 43210" keyboard="phone-pad" />
        <Otp code="482913" />
        <T v="sm">Code filled in for the demo.</T>
        <Btn label="Verify" onPress={advance} />
      </>}
      {i === 1 && <>
        <T v="h2">About you</T>
        <Field label="Full name" value="Simran Kaur" />
        <Field label="Studying or working at" value="Chandigarh University" />
        <T v="label">Looking for</T>
        <Chips>{['Girls PG', 'Co-ed', 'Boys PG'].map(c => <Chip key={c} label={c} on={look === c} onPress={() => setLook(c)} />)}</Chips>
        <Field label="Move-in" value="1 December 2026" />
        <Btn label="Continue" onPress={advance} />
      </>}
      {i === 2 && <>
        <T v="h2">Verify your identity</T>
        <T v="sm">Owners accept only verified residents, and police verification needs it. Your ID goes only to the owner you book with.</T>
        <List>
          <Row left="Aadhaar via DigiLocker" right={<Badge label="Verified" tone="ok" />} />
          <Row left="Selfie match" right={<Badge label="Matched" tone="ok" />} />
          <Row left="College or employer ID" right={<Badge label="Optional" />} last />
        </List>
        <T v="sm">DigiLocker shares a signed copy with your consent. We keep only the last 4 digits of Aadhaar.</T>
        <Btn label="Continue" onPress={advance} />
      </>}
      {i === 3 && <>
        <Hero icon={<Tick />} title="You’re verified" body="Pakka Ghar is free for you. Rent, deposit and electricity are paid only in the app, so every payment is protected and on your record." />
        <Btn label="Continue" onPress={() => { set({ tenantReady: true, role: 'tenant' }); router.replace(((next as string) || '/find') as Href); }} />
      </>}
    </Screen>
  );
}
