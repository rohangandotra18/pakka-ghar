import { Pressable, View } from 'react-native';
import { Btn, Card, Loading, T, C } from '@/design';
import { RADIUS_KM } from './findState';
import { PgCard } from './PgCard';
import type { FindModel } from './useFind';

const plural = (n: number) => `${n} PG${n === 1 ? '' : 's'}`;

/* The sentence above the results: how many, and from where; or why there are none. Empty while the first answer is awaited. */
export function resultHeading(f: FindModel): string {
  const a = f.answer;
  if (!a) return '';
  const n = f.list.length;
  if (n) return a.inArea ? `${plural(n)} in this area` : `${plural(n)} within ${RADIUS_KM} km of ${a.placeName} · nearest first`;
  return a.filtered ? 'No PGs match these filters.' : a.inArea ? 'No PGs in this area yet. Move the map or search another place.' : `No PGs listed near ${a.placeName} yet`;
}

/* Loading, or an error: first load, or a failed reload with the old results still shown. */
export function LoadState({ f }: { f: FindModel }) {
  const { answer, res } = f;
  if (!answer || res.error) return <Loading error={res.error} retry={res.reload} />;
  return null;
}

/* The empty-state helpers, the "Selected on the map" card and the result cards. */
export function ResultCards({ f }: { f: FindModel }) {
  const { answer, list, selected } = f;
  if (!answer) return null;
  const from = answer.inArea ? undefined : answer.placeName;
  return (
    <>
      {list.length === 0 && answer.filtered && <Card><Btn kind="secondary" small label="Clear filters" onPress={f.clearFilters} /></Card>}
      {list.length === 0 && !answer.filtered && !answer.inArea && <Card><T v="sm">Verified PGs show up here as owners list them. Try another place, or check back soon.</T></Card>}
      {selected && (
        <View style={{ gap: 6 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <T v="label">Selected on the map</T>
            <Pressable onPress={() => f.setSelectedId(null)} hitSlop={8} accessibilityRole="button" accessibilityLabel="Clear selected PG" style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center' }}><T v="smBold" style={{ fontSize: 12, color: C.muted }}>✕</T></Pressable>
          </View>
          <PgCard pg={selected} from={from} selected />
        </View>
      )}
      {list.filter(p => p.id !== selected?.id).map(p => (
        <PgCard key={p.id} pg={p} from={from} onHover={on => f.setHoverId(on ? p.id : null)} />
      ))}
    </>
  );
}
