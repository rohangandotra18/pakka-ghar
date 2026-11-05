import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useFonts, Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold } from '@expo-google-fonts/manrope';
import { BricolageGrotesque_600SemiBold, BricolageGrotesque_700Bold } from '@expo-google-fonts/bricolage-grotesque';
import { LiveEvents } from '@/api/events';
import { StoreProvider, useStore } from '@/lib/store';
import { C } from '@/lib/theme';

SplashScreen.preventAutoHideAsync();

/* Saved sessions load before the first screen, so a signed-in owner never sees the welcome screen flash. */
function Booted() {
  const { s } = useStore();
  if (!s.booted) return null;
  /* the same slide animation and background on both platforms */
  return <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right', contentStyle: { backgroundColor: C.bg }, gestureEnabled: true }} />;
}

export default function RootLayout() {
  const [loaded, error] = useFonts({ Manrope_500Medium, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold, BricolageGrotesque_600SemiBold, BricolageGrotesque_700Bold });
  useEffect(() => { if (loaded || error) SplashScreen.hideAsync(); }, [loaded, error]);
  if (!loaded && !error) return null;
  return (
    <SafeAreaProvider>
      <StoreProvider>
        <StatusBar style="dark" />
        <LiveEvents />
        <Booted />
      </StoreProvider>
    </SafeAreaProvider>
  );
}
