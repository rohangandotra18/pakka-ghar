import { router, type Href } from 'expo-router';
import { Pressable, View } from 'react-native';
import { AppBar } from '@/shared';
import { C, Icon, R, Screen, SP, T, type IconName } from '@/design';
import { api, ok, useQuery } from '@/core/api';
import { useStore } from '@/core/session';

/* More: the owner's less frequent places, one tap each. */
export default function More() {
  const { signOut } = useStore();
  const t = useQuery(() => ok(api.GET('/api/owner/today')));
  const repairs = t.data?.open_requests ?? 0;
  const row = (icon: IconName, title: string, sub: string, go: () => void, badge?: number) => (
    <Pressable key={title} onPress={go} accessibilityRole="button" accessibilityLabel={title}
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: SP.md, padding: SP.md, backgroundColor: pressed ? C.bg : C.surface })}>
      <View style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: C.accentSoft, alignItems: 'center', justifyContent: 'center' }}><Icon name={icon} color={C.accent} /></View>
      <View style={{ flex: 1 }}><T v="bodyBold">{title}</T><T v="sm">{sub}</T></View>
      {badge ? <View style={{ minWidth: 22, height: 22, borderRadius: 11, backgroundColor: C.crit, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 }}><T v="smBold" accessibilityLabel={`${badge} new`} style={{ color: C.surface, fontSize: 12 }}>{badge}</T></View> : <T v="sm">›</T>}
    </Pressable>
  );
  const group = (children: React.ReactNode[]) => (
    <View style={{ borderRadius: R.lg, borderWidth: 1, borderColor: C.line, overflow: 'hidden', backgroundColor: C.surface }}>
      {children.map((c, i) => <View key={i} style={{ borderTopWidth: i ? 1 : 0, borderTopColor: C.line }}>{c}</View>)}
    </View>
  );
  const go = (href: Href) => () => router.push(href);
  return (
    <Screen>
        <AppBar />
        <T v="h2">More</T>
        {group([
          row('people', 'Residents', 'Current and past, police, deposits', go('/residents')),
          row('req', 'Repairs', 'Requests from residents', go('/tickets'), repairs),
        ])}
        <T v="label">Your PG</T>
        {group([
          row('stay', 'PG details and pin', 'Name, address, meals, the building on the map', go('/onboarding/owner?step=details')),
          row('beds', 'Rooms and rent', 'Add rooms, rent per bed', go('/onboarding/owner?step=rooms')),
          row('find', 'Photos and papers', 'Camera photos, ownership papers', go('/onboarding/owner?step=photos')),
          row('money', 'Bank account for rent', 'Where payouts go', go('/onboarding/owner?step=payouts')),
          row('today', 'Electricity meters', 'One meter per room', go('/onboarding/owner?step=meters')),
          row('hist', 'Your own agreement', 'Use your PDF instead of the standard one', go('/onboarding/owner?step=agreement')),
        ])}
        {group([
          row('more', 'Sign out', 'You can sign in again with your phone', () => { signOut(); router.replace('/'); }),
        ])}
    </Screen>
  );
}
