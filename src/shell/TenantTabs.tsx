import { Redirect, Tabs } from 'expo-router';
import { TabBar, useWide } from '@/design';
import { useStore } from '@/core/session';

/* The tenant side, for browsing (no account needed) and for residents. On a wide website the site header carries
   these links, so the tab bar is hidden.  An owner signed in on the phone sees
   their dashboard instead; on the website they can switch here from the top bar. */
export default function TenantTabs() {
  const { s } = useStore();
  const wide = useWide();
  if (s.role === 'owner') return <Redirect href="/today" />;
  return (
    <Tabs screenOptions={{ headerShown: false, animation: 'none' }} tabBar={p => (wide ? null : <TabBar {...p} icons={{ find: 'find', stay: 'stay', requests: 'req', history: 'hist' }} />)}>
      <Tabs.Screen name="find" options={{ title: 'Find' }} />
      <Tabs.Screen name="stay" options={{ title: 'My stay' }} />
      <Tabs.Screen name="requests" options={{ title: 'Requests' }} />
      <Tabs.Screen name="history" options={{ title: 'History' }} />
    </Tabs>
  );
}
