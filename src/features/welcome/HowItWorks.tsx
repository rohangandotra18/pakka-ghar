import { View } from 'react-native';
import { T, C, SP } from '@/design';
import { Container, Heading } from './parts';

const STEPS = [
  { title: 'Find and tour', body: 'Search by sector or college, then book a tour at a time the owner has free.' },
  { title: 'Request a bed', body: 'Apply alone or with up to two roommates. The owner sees your verified record and accepts.' },
  { title: 'Sign and pay', body: 'Read and sign the agreement in the app, and pay your deposit into escrow.' },
  { title: 'Live there', body: 'Rent, metered electricity, receipts and repairs in one place. Your deposit comes back from escrow when you leave.' },
];

/* "How renting works": four numbered steps in a row that wrap to two rows when the window is narrow. */
export function HowItWorks() {
  return (
    <Container style={{ gap: SP.xl }}>
      <Heading level={2} v="h2">How renting works</Heading>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: SP.xl }}>
        {STEPS.map((s, i) => (
          <View key={s.title} style={{ flexGrow: 1, flexBasis: 200, minWidth: 200, flex: 1, gap: SP.sm }}>
            <View style={{ width: 32, height: 32, borderRadius: 16, borderWidth: 1.5, borderColor: C.accent, alignItems: 'center', justifyContent: 'center', marginBottom: SP.xs }}>
              <T v="smBold" style={{ color: C.accent }}>{i + 1}</T>
            </View>
            <T v="bodyBold">{s.title}</T>
            <T v="sm" style={{ fontSize: 14, lineHeight: 21 }}>{s.body}</T>
          </View>
        ))}
      </View>
    </Container>
  );
}
