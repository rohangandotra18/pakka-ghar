import { Redirect, Tabs } from 'expo-router';
import { TabBar } from '@/design';
import { useStore } from '@/core/session';

/* The tenant side, for browsing (no account needed) and for residents. An owner signed in on the phone sees
   their dashboard instead; on the website they can switch here from the top bar. */
export default function TenantTabs() {
  const { s } = useStore();
  if (s.role === 'owner') return <Redirect href="/today" />;
  return (
    <Tabs screenOptions={{ headerShown: false, animation: 'none' }} tabBar={p => <TabBar {...p} icons={{ find: 'find', stay: 'stay', requests: 'req', history: 'hist' }} />}>
      <Tabs.Screen name="find" options={{ title: 'Find' }} />
      <Tabs.Screen name="stay" options={{ title: 'My stay' }} />
      <Tabs.Screen name="requests" options={{ title: 'Requests' }} />
      <Tabs.Screen name="history" options={{ title: 'History' }} />
    </Tabs>
  );
}
