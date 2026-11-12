import { AppBar } from '@/shared';
import { Chip, Chips, Screen, T } from '@/design';
import { FilterPanel } from './FilterPanel';
import { FindMap } from './FindMap';
import { LoadState, ResultCards, resultHeading } from './Results';
import { SearchBox } from './SearchBox';
import type { FindModel } from './useFind';

/* Find on phones and narrow windows: everything in one column, the map between the filters and the results. */
export function FindNarrow({ f }: { f: FindModel }) {
  return (
    <Screen>
      <AppBar />
      <T v="h2">Where do you study or work?</T>
      <SearchBox value={f.text} onChange={f.setText} onPick={f.pickPlace} />
      <Chips>
        {f.chips.map(c => <Chip key={c.name} label={c.name} on={f.isChip(c)} onPress={() => f.pickChip(c)} />)}
        <Chip label={f.nFilters ? `Filters · ${f.nFilters}` : 'Filters'} on={f.filtersOpen || f.nFilters > 0} onPress={f.toggleFilters} />
      </Chips>
      {f.filtersOpen && <FilterPanel filters={f.filters} onChange={f.setFilters} />}
      <FindMap place={f.place} area={!!f.area} pgs={f.list} selectedId={f.mapSelectedId} offer={f.offer} onPin={f.setSelectedId} onRegion={f.onRegion} onSearchArea={f.searchArea} />
      <LoadState f={f} />
      {f.answer && <T v="smBold">{resultHeading(f)}</T>}
      <ResultCards f={f} />
    </Screen>
  );
}
