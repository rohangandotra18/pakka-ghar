import { useEffect } from 'react';
import { View } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts } from 'expo-font';
import { LiveEvents } from '@/core/api';
import { StoreProvider, useStore } from '@/core/session';
import { C, FONTS, Toast, useWide } from '@/design';
import { useInOwnerDashboard } from '@/shared';
import { DocumentHead } from './DocumentHead';
import { SiteHeader } from './SiteHeader';

SplashScreen.preventAutoHideAsync();

/* Saved sessions load before the first screen, so a signed-in owner never sees the welcome screen flash.
   On a wide website the site header sits above the stack, so pages scroll under a header that stays put; the
   owner dashboard has its own sidebar and no header. Phones and narrow windows draw just the stack. */
function Booted() {
  const { s } = useStore();
  const wide = useWide();
  const inDashboard = useInOwnerDashboard();
  if (!s.booted) return null;
  /* the same slide animation and background on both platforms */
  return (
    <View style={{ flex: 1 }}>
      {wide && !inDashboard && <SiteHeader />}
      <View style={{ flex: 1 }}>
        <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right', contentStyle: { backgroundColor: C.bg }, gestureEnabled: true }} />
      </View>
    </View>
  );
}

/* Messages after an action or a live event, over whichever screen is showing. */
function Toasts() {
  const { toastMsg } = useStore();
  return <Toast message={toastMsg} />;
}

/* The app's frame: fonts, the signed-in session, live updates, navigation and messages. */
export default function RootLayout() {
  const [loaded, error] = useFonts(FONTS);
  useEffect(() => { if (loaded || error) SplashScreen.hideAsync(); }, [loaded, error]);
  if (!loaded && !error) return null;
  return (
    <SafeAreaProvider>
      <StoreProvider>
        <StatusBar style="dark" />
        <LiveEvents />
        <DocumentHead />
        <Booted />
        <Toasts />
      </StoreProvider>
    </SafeAreaProvider>
  );
}
