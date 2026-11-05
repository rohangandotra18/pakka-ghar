import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { C, T, Wordmark } from '@/design';
import { useStore } from '@/core/session';

/* Top bar on the main screens, with a switch between the tenant and owner sides. Each side keeps its own sign-in. */
export function AppBar() {
  const { s, setRole, ownerReady } = useStore();
  const tenant = s.role === 'tenant';
  const first = (n?: string) => (n ? n.split(' ')[0] : '');
  const swap = () => {
    const next = tenant ? 'owner' : 'tenant';
    setRole(next);
    router.replace(next === 'tenant' ? '/find' : (ownerReady ? '/today' : '/onboarding/owner'));
  };
  const label = tenant
    ? (s.tenant ? `${first(s.tenant.me.name) || 'You'} · Tenant` : 'Browsing · Tenant')
    : `${first(s.owner?.me.name) || 'Owner'} · Owner`;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
      <Wordmark size={28} />
      <Pressable onPress={swap} accessibilityRole="button" accessibilityLabel={`${label}. Switch to the ${tenant ? 'owner' : 'tenant'} side`} style={{ borderRadius: 999, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, paddingHorizontal: 11, paddingVertical: 6 }}>
        <T v="smBold" style={{ fontSize: 12 }}>{label}  ⇄</T>
      </Pressable>
    </View>
  );
}
