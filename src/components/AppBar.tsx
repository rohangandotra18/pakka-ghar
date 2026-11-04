import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { C } from '@/lib/theme';
import { useStore } from '@/lib/store';
import { T } from './ui';
import { Wordmark } from './icons';

/* Top bar on the main screens, with a demo switch between the tenant and owner sides of one account. */
export function AppBar() {
  const { s, set } = useStore();
  const tenant = s.role === 'tenant';
  const swap = () => {
    const next = tenant ? 'owner' : 'tenant';
    set({ role: next });
    router.replace(next === 'tenant' ? '/find' : (s.ownerReady ? '/today' : '/onboarding/owner'));
  };
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
      <Wordmark size={28} />
      <Pressable onPress={swap} accessibilityRole="button" style={{ borderRadius: 999, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, paddingHorizontal: 11, paddingVertical: 6 }}>
        <T v="smBold" style={{ fontSize: 12 }}>{tenant ? (s.tenantReady ? 'Simran · Tenant' : 'Browsing · Tenant') : 'Jatinder · Owner'}  ⇄</T>
      </Pressable>
    </View>
  );
}
