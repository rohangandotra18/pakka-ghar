import { Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { BottomTabBarProps } from 'expo-router/build/layouts/TabsClient';
import { C } from './theme';
import { Icon, type IconName } from './icons';
import { T } from './ui';

/* Our own tab bar, so it's the same height, icons and type on iOS and Android. */
/* `only` limits the bar to those tabs (others stay reachable by link); `lit` highlights a tab for a screen that
   belongs under it (Residents under More). */
export function TabBar({ state, descriptors, navigateToTab, icons, only, lit }: BottomTabBarProps & { icons: Record<string, IconName>; only?: string[]; lit?: string }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={{ flexDirection: 'row', backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.line, paddingTop: 8, paddingBottom: Math.max(insets.bottom, 10) }}>
      {state.routes.map((route, i) => {
        if (only && !only.includes(route.name)) return null;
        const focused = lit ? route.name === lit : state.index === i;
        const label = descriptors[route.key].options.title ?? route.name;
        const color = focused ? C.accent : C.muted;
        return (
          <Pressable key={route.key} accessibilityRole="tab" accessibilityState={{ selected: focused }} style={{ flex: 1, alignItems: 'center', gap: 3 }}
            onPress={() => { if (state.index !== i) navigateToTab(route.key); }}>
            <Icon name={icons[route.name] ?? 'find'} color={color} />
            <T v="label" style={{ color, fontSize: 11 }}>{String(label)}</T>
          </Pressable>
        );
      })}
    </View>
  );
}
