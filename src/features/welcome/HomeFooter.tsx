import { View } from 'react-native';
import { router } from 'expo-router';
import { Wordmark, T, C, SP } from '@/design';
import { Container, TextLink } from './parts';

/* The same destination as the site header's Sign in */
const SIGN_IN = { pathname: '/onboarding/tenant', params: { why: 'signin' } } as const;

export function HomeFooter() {
  return (
    <View style={{ borderTopWidth: 1, borderTopColor: C.line, paddingVertical: 40 }}>
      <Container style={{ gap: SP.xl }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: SP.xl, flexWrap: 'wrap' }}>
          <View style={{ gap: SP.sm }}>
            <Wordmark size={30} />
            <T v="sm">Verified PGs in Chandigarh, Mohali and Panchkula.</T>
          </View>
          <View style={{ flexDirection: 'row', gap: SP.xl }}>
            <TextLink muted label="Find a PG" onPress={() => router.push('/find')} />
            <TextLink muted label="List your PG" onPress={() => router.push('/onboarding/owner')} />
            <TextLink muted label="Sign in" onPress={() => router.push(SIGN_IN)} />
          </View>
        </View>
        <T v="sm">© 2026 Pakka Ghar · Map data © OpenStreetMap contributors</T>
      </Container>
    </View>
  );
}
