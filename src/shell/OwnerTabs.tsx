import { Redirect, Tabs, router, usePathname, type Href } from 'expo-router';
import { Pressable, View } from 'react-native';
import { C, Icon, R, SP, T, TabBar, Wordmark, useWide, type IconName } from '@/design';
import { api, ok, useQuery } from '@/core/api';
import { useStore } from '@/core/session';

/* The owner side: Home, Requests, Beds, Money, More. Residents and repairs open from More (and Home) but keep the
   tab bar, with More lit. On a wide website the tabs become a sidebar, which also carries the switch to the
   tenant side. Shown to an account that runs a PG; anyone else is sent to the tenant side. */
const TABS: { name: string; title: string; icon: IconName }[] = [
  { name: 'today', title: 'Home', icon: 'home' },
  { name: 'applications', title: 'Requests', icon: 'inbox' },
  { name: 'beds', title: 'Beds', icon: 'beds' },
  { name: 'money', title: 'Money', icon: 'money' },
  { name: 'more', title: 'More', icon: 'more' },
];
const UNDER_MORE = ['residents', 'tickets', 'tour-hours'];

function Sidebar() {
  const path = usePathname();
  const { s, setRole } = useStore();
  const t = useQuery(() => ok(api.GET('/api/owner/today')));
  const counts: Record<string, number> = { applications: t.data?.applications ?? 0, tickets: t.data?.open_requests ?? 0 };
  const items = [...TABS.filter(x => x.name !== 'more'), { name: 'residents', title: 'Residents', icon: 'people' as IconName },
    { name: 'tickets', title: 'Repairs', icon: 'req' as IconName }, { name: 'more', title: 'PG settings', icon: 'more' as IconName }];
  return (
    <View style={{ width: 232, backgroundColor: C.surface, borderRightWidth: 1, borderRightColor: C.line, padding: SP.lg, gap: 4 }}>
      <View style={{ marginBottom: SP.lg }}><Wordmark size={26} /></View>
      {items.map(it => {
        const on = path === `/${it.name}`;
        const n = counts[it.name] ?? 0;
        return (
          <Pressable key={it.name} onPress={() => router.navigate(`/${it.name}` as Href)} accessibilityRole="link" accessibilityState={{ selected: on }}
            style={({ hovered }: { hovered?: boolean }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 10, paddingVertical: 9, borderRadius: R.sm,
              backgroundColor: on ? C.accentSoft : hovered ? C.bg : 'transparent' })}>
            <Icon name={it.icon} color={on ? C.accent : C.muted} size={20} />
            <T v="bodyBold" style={{ flex: 1, color: on ? C.accent : C.ink }}>{it.title}</T>
            {n > 0 && <View style={{ minWidth: 20, height: 20, borderRadius: 10, backgroundColor: C.crit, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 5 }}>
              <T v="smBold" accessibilityLabel={`${n} new`} style={{ color: C.surface, fontSize: 11 }}>{n}</T></View>}
          </Pressable>
        );
      })}
      <View style={{ flex: 1 }} />
      <Pressable onPress={() => { setRole('tenant'); router.replace('/find'); }} accessibilityRole="button"
        style={{ borderWidth: 1, borderColor: C.line, borderStyle: 'dashed', borderRadius: R.sm, padding: 10, gap: 2 }}>
        <T v="smBold">⇄ Switch to tenant side</T>
        <T v="sm" style={{ fontSize: 12 }}>Browse and rent as {s.session?.me.name?.split(' ')[0] || 'yourself'}</T>
      </Pressable>
    </View>
  );
}

export default function OwnerTabs() {
  const { s } = useStore();
  const wide = useWide();
  const path = usePathname();
  if (s.role !== 'owner') return <Redirect href="/find" />;
  const lit = UNDER_MORE.includes(path.slice(1)) ? 'more' : undefined;
  const tabs = (
    <Tabs screenOptions={{ headerShown: false, animation: 'none' }}
      tabBar={p => (wide ? null : <TabBar {...p} only={TABS.map(x => x.name)} lit={lit} icons={Object.fromEntries(TABS.map(x => [x.name, x.icon]))} />)}>
      {TABS.map(x => <Tabs.Screen key={x.name} name={x.name} options={{ title: x.title }} />)}
      <Tabs.Screen name="residents" options={{ title: 'Residents' }} />
      <Tabs.Screen name="tickets" options={{ title: 'Repairs' }} />
      <Tabs.Screen name="tour-hours" options={{ title: 'Tour hours' }} />
    </Tabs>
  );
  if (!wide) return tabs;
  return <View style={{ flex: 1, flexDirection: 'row', backgroundColor: C.bg }}><Sidebar /><View style={{ flex: 1 }}>{tabs}</View></View>;
}
