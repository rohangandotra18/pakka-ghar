import { useState } from 'react';
import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { Btn, Hero, Screen, T } from '@/components/ui';
import { Logo } from '@/components/icons';
import { useStore } from '@/lib/store';
import { C, R, SP } from '@/lib/theme';

/* Welcome: one account, two sides. The choice decides which onboarding runs first. */
export default function Welcome() {
  const { set } = useStore();
  const [role, setRole] = useState<'tenant' | 'owner'>('tenant');
  const opt = (r: 'tenant' | 'owner', label: string) => (
    <Pressable onPress={() => setRole(r)} accessibilityRole="radio" accessibilityState={{ checked: role === r }}
      style={{ borderWidth: 1.5, borderColor: role === r ? C.accent : C.line, backgroundColor: role === r ? C.accentSoft : C.surface, borderRadius: R.md, padding: SP.lg }}>
      <T v="bodyBold">{label}</T>
    </Pressable>
  );
  return (
    <Screen>
      <Hero icon={<Logo size={72} />} title="Find a PG you can trust" body="Verified owners, real rent per bed, and your rent, electricity and agreement in one place. Free for everyone. No cash, ever." />
      <View style={{ gap: SP.sm }}>{opt('tenant', "I'm looking for a place")}{opt('owner', 'I own a PG or flat')}</View>
      <Btn label="Get started" onPress={() => { set({ role }); router.replace(role === 'tenant' ? '/find' : '/onboarding/owner'); }} />
    </Screen>
  );
}
