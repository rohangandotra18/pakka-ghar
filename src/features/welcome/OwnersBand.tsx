import { View } from 'react-native';
import { router } from 'expo-router';
import { Btn, Icon, T, C, SP } from '@/design';
import { Container, Heading } from './parts';

const POINTS = [
  'Tenants arrive with a verified ID and rental record',
  'Rent settles to your bank account, with no cash to chase',
  'Agreements, police verification and repairs handled in the app',
];

/* The owners' invitation: a full-width soft band, the pitch at the left, the button at the right. */
export function OwnersBand() {
  return (
    <View style={{ backgroundColor: C.accentSoft, paddingVertical: 56 }}>
      <Container style={{ flexDirection: 'row', alignItems: 'center', gap: 48 }}>
        <View style={{ flex: 1, minWidth: 0, gap: SP.md }}>
          <Heading level={2} v="h2">Own a PG or flat? List it free</Heading>
          {POINTS.map(p => (
            <View key={p} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Icon name="tick" color={C.accent} size={20} />
              <T style={{ flex: 1 }}>{p}</T>
            </View>
          ))}
        </View>
        <View style={{ width: 280, gap: SP.sm }}>
          <Btn label="List your PG" onPress={() => router.push('/onboarding/owner')} />
          <T v="sm" style={{ textAlign: 'center', color: C.muted }}>Free. Goes live once our trust team has checked it.</T>
        </View>
      </Container>
    </View>
  );
}
