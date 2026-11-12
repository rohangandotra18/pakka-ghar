import { Redirect, router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { Btn, Hero, Screen, T, Logo, C, SP, useWide } from '@/design';
import { useStore } from '@/core/session';
import { DesktopHome } from './DesktopHome';

/* Welcome: one app for tenants and owners. Signing in decides what you see: an account that runs a PG opens on
   the owner dashboard, everyone else on Find. Someone signed in never sees this screen. */
export default function Welcome() {
  const { s } = useStore();
  const wide = useWide();
  if (s.role === 'owner') return <Redirect href="/today" />;
  if (s.role === 'tenant') return <Redirect href="/find" />;
  if (wide) return <DesktopHome />;
  return (
    <Screen>
      <Hero icon={<Logo size={72} />} title="Find a PG you can trust" body="Verified owners, real rent per bed, and your rent, electricity and agreement in one place. Free for everyone. No cash, ever." />
      <View style={{ gap: SP.sm }}>
        <Btn label="Start looking" onPress={() => router.replace('/find')} />
        <Btn kind="secondary" label="Sign in" onPress={() => router.push({ pathname: '/onboarding/tenant', params: { why: 'signin' } })} />
      </View>
      <Pressable accessibilityRole="button" onPress={() => router.push('/onboarding/owner')} style={{ alignSelf: 'center', padding: SP.sm }}>
        <T v="smBold" style={{ color: C.accent }}>Own a PG or flat? List it free</T>
      </Pressable>
    </Screen>
  );
}
