import { useState } from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { SP } from '@/design';
import { PgCard } from '@/features/search';
import { useFreeListings } from './useHomeListings';
import { Container, Heading, TextLink } from './parts';

const GAP = 16;

/* two to a row: the photo card needs about 500 px for its price, badge and one-line details to sit without wrapping */
const PER_ROW = 2;

/* PGs with a bed free now: up to six cards, two to a row. Nothing is drawn while loading, if the request fails or if
   there are none. */
export function FreeNow() {
  const { list } = useFreeListings();
  const perRow = PER_ROW;
  const [w, setW] = useState(0);
  if (!list || !list.length) return null;
  const cell = w ? Math.floor((w - GAP * (perRow - 1)) / perRow) : 0;
  return (
    <Container style={{ gap: SP.lg }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: SP.lg }}>
        <Heading level={2} v="h2">PGs with beds free now</Heading>
        <TextLink label="See all on the map" onPress={() => router.push('/find')} />
      </View>
      <View onLayout={e => setW(e.nativeEvent.layout.width)} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: GAP }}>
        {w > 0 && list.map(pg => <View key={pg.id} style={{ width: cell }}><PgCard pg={pg} /></View>)}
      </View>
    </Container>
  );
}
