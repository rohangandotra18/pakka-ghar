import { View } from 'react-native';
import { Icon, T, C, SP, type IconName } from '@/design';
import { Container, Heading } from './parts';

const ITEMS: { icon: IconName; title: string; body: string }[] = [
  { icon: 'shield', title: "Checked before it's listed", body: "Our trust team checks the owner's papers and the building's location before a PG appears here." },
  { icon: 'camera', title: 'Photos taken on site', body: 'Every photo is taken at the building with the Pakka Ghar camera. No stock, edited or AI pictures.' },
  { icon: 'money', title: 'No cash, no brokerage', body: 'Rent and deposit are paid in the app, and the deposit is held in escrow. Pakka Ghar is free for tenants and owners.' },
];

/* Three things that make a listing here different, in equal columns. */
export function Assurances() {
  return (
    <Container>
      <View style={{ flexDirection: 'row', gap: SP.xl }}>
        {ITEMS.map(i => (
          <View key={i.title} style={{ flex: 1, minWidth: 0, gap: SP.md }}>
            <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: C.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Icon name={i.icon} color={C.accent} size={22} />
            </View>
            <Heading level={3} v="h3">{i.title}</Heading>
            <T v="sm" style={{ fontSize: 14, lineHeight: 21 }}>{i.body}</T>
          </View>
        ))}
      </View>
    </Container>
  );
}
