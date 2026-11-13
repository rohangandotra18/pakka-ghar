import { router } from 'expo-router';
import { Image, Pressable, View } from 'react-native';
import { Badge, Dot, T, C, GENDER_COLOR, R } from '@/design';
import { inr, type Schemas } from '@/core/api';
import { mediaUrl } from '@/core/device';

const PHOTO = { width: 132, height: 104, borderRadius: 10 } as const;
type PressState = { hovered?: boolean; pressed?: boolean };

/* A result on a wide website: the PG's first photo at the left, its details at the right. Hovering darkens the border and
   (through onHover) lights the PG's pin on the map; the selected card keeps the accent border. */
export function PgCardWide({ pg, from, selected, onHover }: { pg: Schemas['ListingOut']; from?: string; selected?: boolean; onHover?: (on: boolean) => void }) {
  const photo = pg.photos[0];
  return (
    <Pressable onPress={() => router.push(`/pg/${pg.id}`)} onHoverIn={onHover && (() => onHover(true))} onHoverOut={onHover && (() => onHover(false))}
      accessibilityRole="button" accessibilityLabel={`${pg.name}, ${inr(pg.rent_paise)} per bed, ${pg.area}${pg.rating != null ? `, rated ${pg.rating.toFixed(1)} from ${pg.stays} ${pg.stays === 1 ? 'stay' : 'stays'}` : ''}`}
      style={({ hovered, pressed }: PressState) => ({
        flexDirection: 'row', gap: 14, backgroundColor: C.surface, borderRadius: R.lg, padding: selected ? 11 : 12,
        borderWidth: selected ? 2 : 1, borderColor: selected ? C.accent : hovered ? C.ink : C.line, opacity: pressed ? 0.85 : 1,
      })}>
      {photo ? (
        <Image source={{ uri: mediaUrl(photo.thumb) }} resizeMode="cover" accessibilityLabel={photo.caption || `Photo of ${pg.name}`} style={{ ...PHOTO, backgroundColor: C.surface2 }} />
      ) : (
        <View style={{ ...PHOTO, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center' }}><T v="sm" style={{ fontSize: 12, color: C.muted }}>No photos yet</T></View>
      )}
      <View style={{ flex: 1, minWidth: 0, gap: 4 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <T v="price">{inr(pg.rent_paise)}<T v="sm"> /bed</T></T>
          {pg.hot ? <Badge label="High demand" tone="warn" /> : <Badge label={`${pg.free} free`} tone="ok" />}
        </View>
        <T v="bodyBold" numberOfLines={1}>{pg.name}</T>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Dot color={GENDER_COLOR[pg.gender]} /><T v="sm" numberOfLines={1}>{pg.gender} · {pg.meals} · {pg.area}</T></View>
        {from && pg.km != null ? <T v="smBold" style={{ color: C.accent }}>{pg.km} km from {from}</T> : null}
        {pg.rating != null ? <T v="sm" style={{ color: C.muted }}>★ {pg.rating.toFixed(1)} · {pg.stays} {pg.stays === 1 ? 'stay' : 'stays'}</T> : null}
      </View>
    </Pressable>
  );
}
