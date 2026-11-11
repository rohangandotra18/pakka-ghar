import { useCallback, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';
import { AppBar, type Bounds, type MapRegion } from '@/shared';
import { Btn, Card, Chip, Chips, Loading, Screen, T, C } from '@/design';
import { api, ok, useQuery } from '@/core/api';
import { FilterPanel } from './FilterPanel';
import { FindMap } from './FindMap';
import { PgCard } from './PgCard';
import { SearchBox } from './SearchBox';
import { RADIUS_KM, areaOffer, buildListingsQuery, countFilters, placeChips, roundBounds, samePlace, type Filters, type Place } from './findState';

/* Places people search from until the server's list arrives. */
const NEAR: Place[] = [
  { name: 'PGIMER', lat: 30.7649, lng: 76.7757 },
  { name: 'Panjab University', lat: 30.7605, lng: 76.766 },
  { name: 'Sector 17', lat: 30.7412, lng: 76.7788 },
];

const plural = (n: number) => `${n} PG${n === 1 ? '' : 's'}`;

/* Find is always in one of two modes: around a chosen place (area is null), or inside the part of the map the person
   asked to search (area is set). The place stays set in area mode so the map's camera stays where it was. */
export default function Find() {
  const [place, setPlace] = useState<Place>(NEAR[0]);
  const [area, setArea] = useState<Bounds | null>(null);
  const [filters, setFilters] = useState<Filters>({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [text, setText] = useState('');
  const [region, setRegion] = useState<MapRegion | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  /* the server filters and sorts; each answer remembers what it was asked, so the heading never describes the next search */
  const { gender, rent, kind } = filters;
  const areaKey = area ? JSON.stringify(area) : '';
  const res = useQuery(async () => {
    const f: Filters = { gender, rent, kind };
    const list = await ok(api.GET('/api/listings', { params: { query: buildListingsQuery({ place, area, filters: f }) } }));
    return { list, inArea: !!area, placeName: place.name, filtered: countFilters(f) > 0 };
  }, [place, areaKey, gender, rent, kind]);
  const popular = useQuery(() => ok(api.GET('/api/places')), []);

  const answer = res.data;
  const list = useMemo(() => answer?.list ?? [], [answer]);
  const selected = list.find(p => p.id === selectedId);
  /* a new search that no longer has the selected PG drops the selection (state adjusted while rendering, not in an effect) */
  if (answer && selectedId && !selected) setSelectedId(null);

  const choosePlace = useCallback((p: Place) => { setPlace(p); setArea(null); setRegion(null); setSelectedId(null); }, []);
  const chips = placeChips(popular.data?.map(p => ({ name: p.name, lat: p.lat, lng: p.lng })), NEAR, place);
  const offer = areaOffer(region, area);
  const nFilters = countFilters(filters);
  const clearFilters = () => setFilters({});

  return (
    <Screen>
      <AppBar />
      <T v="h2">Where do you study or work?</T>
      <SearchBox value={text} onChange={setText} onPick={choosePlace} />
      <Chips>
        {chips.map(c => <Chip key={c.name} label={c.name} on={samePlace(c, place)} onPress={() => { setText(''); choosePlace(c); }} />)}
        <Chip label={nFilters ? `Filters · ${nFilters}` : 'Filters'} on={filtersOpen || nFilters > 0} onPress={() => setFiltersOpen(o => !o)} />
      </Chips>
      {filtersOpen && <FilterPanel filters={filters} onChange={setFilters} />}
      <FindMap place={place} area={!!area} pgs={list} selectedId={hoverId ?? selectedId} offer={offer} onPin={setSelectedId} onRegion={setRegion}
        onSearchArea={() => { if (region) setArea(roundBounds(region.bounds)); }} />
      {!answer && <Loading error={res.error} retry={res.reload} />}
      {answer && res.error && <Loading error={res.error} retry={res.reload} />}
      {answer && (
        <>
          <T v="smBold">{list.length ? (answer.inArea ? `${plural(list.length)} in this area` : `${plural(list.length)} within ${RADIUS_KM} km of ${answer.placeName} · nearest first`) : answer.filtered ? 'No PGs match these filters.' : answer.inArea ? 'No PGs in this area yet. Move the map or search another place.' : `No PGs listed near ${answer.placeName} yet`}</T>
          {list.length === 0 && answer.filtered && <Card><Btn kind="secondary" small label="Clear filters" onPress={clearFilters} /></Card>}
          {list.length === 0 && !answer.filtered && !answer.inArea && <Card><T v="sm">Verified PGs show up here as owners list them. Try another place, or check back soon.</T></Card>}
          {selected && (
            <View style={{ gap: 6 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <T v="label">Selected on the map</T>
                <Pressable onPress={() => setSelectedId(null)} hitSlop={8} accessibilityRole="button" accessibilityLabel="Clear selected PG" style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: C.surface2, alignItems: 'center', justifyContent: 'center' }}><T v="smBold" style={{ fontSize: 12, color: C.muted }}>✕</T></Pressable>
              </View>
              <PgCard pg={selected} from={answer.inArea ? undefined : answer.placeName} selected />
            </View>
          )}
          {list.filter(p => p.id !== selected?.id).map(p => (
            <PgCard key={p.id} pg={p} from={answer.inArea ? undefined : answer.placeName} onHover={on => setHoverId(on ? p.id : null)} />
          ))}
        </>
      )}
    </Screen>
  );
}
