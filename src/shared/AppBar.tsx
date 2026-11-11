import { useState } from 'react';
import { Platform, Pressable, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import { C, R, SP, T, Wordmark } from '@/design';
import { useStore } from '@/core/session';

/* Top bar on the main screens, with the account menu. The side shown follows the account; only the website lets
   an owner switch between their dashboard and the tenant side. */
export function AppBar() {
  const { s, setRole, canSwitch, ownerReady, signOut } = useStore();
  const [open, setOpen] = useState(false);
  const { width } = useWindowDimensions();
  /* on the wide website the owner's sidebar already carries the logo */
  const sidebar = Platform.OS === 'web' && width >= 900 && s.role === 'owner';
  const me = s.session?.me;
  const first = me?.name ? me.name.split(' ')[0] : '';
  const owner = s.role === 'owner';
  const label = !me ? 'Sign in' : `${first || 'You'}${canSwitch ? ` · ${owner ? 'Owner' : 'Tenant'}` : ''}`;
  const go = (fn: () => void) => () => { setOpen(false); fn(); };
  const items: { label: string; onPress: () => void }[] = [];
  if (canSwitch) items.push({ label: owner ? 'Switch to tenant side' : 'Switch to owner dashboard', onPress: go(() => { const next = owner ? 'tenant' : 'owner'; setRole(next); router.replace(next === 'owner' ? '/today' : '/find'); }) });
  if (me && !ownerReady) items.push({ label: 'List your PG', onPress: go(() => router.push('/onboarding/owner')) });
  if (me?.staff) items.push({ label: 'Trust team', onPress: go(() => router.push('/staff')) });
  if (me) items.push({ label: 'Sign out', onPress: go(() => { signOut(); router.replace('/'); }) });
  return (
    <View style={{ marginBottom: 2, zIndex: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        {sidebar ? <View /> : <Wordmark size={28} />}
        <Pressable onPress={me ? () => setOpen(o => !o) : () => router.push({ pathname: '/onboarding/tenant', params: { why: 'signin' } })}
          accessibilityRole="button" accessibilityLabel={me ? `${label}. Account menu` : 'Sign in'} accessibilityState={{ expanded: open }}
          style={{ borderRadius: 999, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, paddingHorizontal: 11, paddingVertical: 6 }}>
          <T v="smBold" style={{ fontSize: 12 }}>{label}{me ? (canSwitch ? '  ⇄' : '  ▾') : ''}</T>
        </Pressable>
      </View>
      {open && (
        <View style={{ alignSelf: 'flex-end', marginTop: 6, backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: R.md, paddingVertical: 4, minWidth: 200 }}>
          {items.map((it, i) => (
            <Pressable key={it.label} onPress={it.onPress} accessibilityRole="button"
              style={{ paddingHorizontal: SP.md, paddingVertical: 10, borderTopWidth: i ? 1 : 0, borderTopColor: C.line }}>
              <T v="bodyBold" style={{ color: it.label === 'Sign out' ? C.crit : C.ink }}>{it.label}</T>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}
