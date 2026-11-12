import { useRef } from 'react';
import { ScrollView, View, useWindowDimensions, type ScrollViewInstance } from 'react-native';
import { Chip, Chips, Screen, T, C } from '@/design';
import { FilterPanel } from './FilterPanel';
import { FindMap } from './FindMap';
import { LoadState, ResultCards, resultHeading } from './Results';
import { SearchBox } from './SearchBox';
import type { FindModel } from './useFind';

/* Find on a wide website: the results in a pane of their own at the left, the map taking the rest, both as tall as the
   window under the site header, so the page itself never scrolls. */
export function FindWide({ f }: { f: FindModel }) {
  const roomy = useWindowDimensions().width >= 1200;
  const list = useRef<ScrollViewInstance>(null);
  /* a pin pressed on the map puts its card at the top of the list, so the person sees it */
  const onPin = (id: string) => { f.setSelectedId(id); list.current?.scrollTo({ y: 0, animated: true }); };
  return (
    <Screen width="full" scroll={false}>
      <View style={{ flex: 1, flexDirection: 'row', minHeight: 0 }}>
        <ScrollView ref={list} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator
          style={{ flexGrow: 0, flexShrink: 0, width: roomy ? 520 : 420, borderRightWidth: 1, borderRightColor: C.line }}
          contentContainerStyle={{ padding: 24, gap: 12 }}>
          <View style={{ gap: 4 }}>
            <T v="h2">Find a PG</T>
            {f.answer && <T v="sm">{resultHeading(f)}</T>}
          </View>
          <SearchBox value={f.text} onChange={f.setText} onPick={f.pickPlace} />
          <Chips>
            {f.chips.map(c => <Chip key={c.name} label={c.name} on={f.isChip(c)} onPress={() => f.pickChip(c)} />)}
            <Chip label={f.nFilters ? `Filters · ${f.nFilters}` : 'Filters'} on={f.filtersOpen || f.nFilters > 0} onPress={f.toggleFilters} />
          </Chips>
          {f.filtersOpen && <FilterPanel filters={f.filters} onChange={f.setFilters} />}
          <LoadState f={f} />
          <ResultCards f={f} />
        </ScrollView>
        <View style={{ flex: 1, minWidth: 0 }}>
          <FindMap place={f.place} area={!!f.area} pgs={f.list} selectedId={f.mapSelectedId} offer={f.offer} onPin={onPin} onRegion={f.onRegion} onSearchArea={f.searchArea} />
        </View>
      </View>
    </Screen>
  );
}
