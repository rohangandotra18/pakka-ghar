import { Tabs } from 'expo-router';
import { TabBar } from '@/components/TabBar';

export default function TenantTabs() {
  return (
    <Tabs screenOptions={{ headerShown: false, animation: 'none' }} tabBar={p => <TabBar {...p} icons={{ find: 'find', stay: 'stay', requests: 'req', history: 'hist' }} />}>
      <Tabs.Screen name="find" options={{ title: 'Find' }} />
      <Tabs.Screen name="stay" options={{ title: 'My stay' }} />
      <Tabs.Screen name="requests" options={{ title: 'Requests' }} />
      <Tabs.Screen name="history" options={{ title: 'History' }} />
    </Tabs>
  );
}
