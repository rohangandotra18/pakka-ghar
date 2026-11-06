import { Redirect, Tabs } from 'expo-router';
import { TabBar } from '@/design';
import { useStore } from '@/core/session';

/* The owner side. Shown to an account that runs a PG; anyone else is sent to the tenant side. */
export default function OwnerTabs() {
  const { s } = useStore();
  if (s.role !== 'owner') return <Redirect href="/find" />;
  return (
    <Tabs screenOptions={{ headerShown: false, animation: 'none' }} tabBar={p => <TabBar {...p} icons={{ today: 'today', beds: 'beds', money: 'money', residents: 'people', tickets: 'req' }} />}>
      <Tabs.Screen name="today" options={{ title: 'Today' }} />
      <Tabs.Screen name="beds" options={{ title: 'Beds' }} />
      <Tabs.Screen name="money" options={{ title: 'Money' }} />
      <Tabs.Screen name="residents" options={{ title: 'Residents' }} />
      <Tabs.Screen name="tickets" options={{ title: 'Requests' }} />
    </Tabs>
  );
}
