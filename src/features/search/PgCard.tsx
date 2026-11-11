import { router } from 'expo-router';
import { Pressable, View } from 'react-native';
import { Badge, Dot, T, C, GENDER_COLOR, R } from '@/design';
import { inr, type Schemas } from '@/core/api';

/* One PG in the results: price, free beds, name, who it's for and where. `from` adds how far it is from the chosen place. */
export function PgCard({ pg, from, selected, onHover }: { pg: Schemas['ListingOut']; from?: string; selected?: boolean; onHover?: (on: boolean) => void }) {
  return (
    <Pressable onPress={() => router.push(`/pg/${pg.id}`)} onHoverIn={onHover && (() => onHover(true))} onHoverOut={onHover && (() => onHover(false))}
      accessibilityRole="button" accessibilityLabel={`${pg.name}, ${inr(pg.rent_paise)} per bed, ${pg.area}`}
      style={({ pressed }) => ({ backgroundColor: C.surface, borderRadius: R.lg, borderWidth: selected ? 2 : 1, borderColor: selected ? C.accent : C.line, padding: selected ? 13 : 14, gap: 4, opacity: pressed ? 0.85 : 1 })}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <T v="price">{inr(pg.rent_paise)}<T v="sm"> /bed</T></T>
        {pg.hot ? <Badge label="High demand" tone="warn" /> : <Badge label={`${pg.free} free`} tone="ok" />}
      </View>
      <T v="bodyBold">{pg.name}</T>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Dot color={GENDER_COLOR[pg.gender]} /><T v="sm">{pg.gender} · {pg.meals} · {pg.area}</T></View>
      {from && pg.km != null ? <T v="smBold" style={{ color: C.accent }}>{pg.km} km from {from}</T> : null}
    </Pressable>
  );
}
