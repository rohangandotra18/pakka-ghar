import { useEffect, useRef, useState, type ElementRef, type ReactNode } from 'react';
import { Platform, Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { C, R, SP, T } from '@/design';
import { useStore } from '@/core/session';

/* The account button and its menu: the name, then "Switch side" when the account allows it, "List your PG", "Trust
   team" for staff and "Sign out". Signed out, the button is "Sign in".
   Two ways to show it:
   - inline (phones, the default): the menu opens under the row and pushes the page down. `left` is whatever sits at
     the left of that row (the logo).
   - `floating` (the website's header): the menu is a dropdown under the button, above the page, so it never changes
     the height of the bar. It closes when an item is chosen, on Escape, or on a click anywhere else. */
export function AccountMenu({ floating, left }: { floating?: boolean; left?: ReactNode }) {
  const { s, setRole, canSwitch, ownerReady, signOut } = useStore();
  const [open, setOpen] = useState(false);
  const box = useRef<ElementRef<typeof View>>(null);
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

  /* the dropdown closes on Escape and on a press anywhere outside the button and menu */
  useEffect(() => {
    if (!floating || !open || Platform.OS !== 'web') return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    const onDown = (e: PointerEvent) => {
      const el = box.current as unknown as Node | null;   // on the web a View is a DOM element
      if (el && e.target instanceof Node && !el.contains(e.target)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('pointerdown', onDown); };
  }, [floating, open]);

  const button = (
    <Pressable onPress={me ? () => setOpen(o => !o) : () => router.push({ pathname: '/onboarding/tenant', params: { why: 'signin' } })}
      accessibilityRole="button" accessibilityLabel={me ? `${label}. Account menu` : 'Sign in'} accessibilityState={{ expanded: open }}
      style={{ borderRadius: 999, borderWidth: 1, borderColor: C.line, backgroundColor: C.surface, paddingHorizontal: 11, paddingVertical: 6 }}>
      <T v="smBold" style={{ fontSize: 12 }}>{label}{me ? (canSwitch ? '  ⇄' : '  ▾') : ''}</T>
    </Pressable>
  );
  const menu = (style: object) => (
    <View style={[{ backgroundColor: C.surface, borderWidth: 1, borderColor: C.line, borderRadius: R.md, paddingVertical: 4, minWidth: 200 }, style]}>
      {items.map((it, i) => (
        <Pressable key={it.label} onPress={it.onPress} accessibilityRole="button"
          style={({ hovered }: { hovered?: boolean }) => ({ paddingHorizontal: SP.md, paddingVertical: 10, borderTopWidth: i ? 1 : 0, borderTopColor: C.line, backgroundColor: hovered ? C.bg : 'transparent' })}>
          <T v="bodyBold" style={{ color: it.label === 'Sign out' ? C.crit : C.ink }}>{it.label}</T>
        </Pressable>
      ))}
    </View>
  );

  if (floating) {
    return (
      <View ref={box} style={{ position: 'relative', zIndex: 30 }}>
        {button}
        {open && menu({ position: 'absolute', top: '100%', right: 0, marginTop: 8, minWidth: 220, zIndex: 30 })}
      </View>
    );
  }
  return (
    <View style={{ marginBottom: 2, zIndex: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        {left ?? <View />}
        {button}
      </View>
      {open && menu({ alignSelf: 'flex-end', marginTop: 6 })}
    </View>
  );
}
