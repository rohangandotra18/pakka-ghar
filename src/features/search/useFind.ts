import { useCallback, useMemo, useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';
import type { Bounds, MapRegion } from '@/shared';
import { useWide } from '@/design';
import { api, ok, useQuery } from '@/core/api';
import { BUILT_IN_PLACES, usePopularPlaces } from './usePopularPlaces';
import { areaOffer, buildListingsQuery, countFilters, findHref, parsePlaceParams, placeChips, roundBounds, sameSpot, samePlace, type Filters, type Place } from './findState';

/* Find is always in one of two modes: around a chosen place (area is null), or inside the part of the map the person
   asked to search (area is set). The place stays set in area mode so the map's camera stays where it was.
   This hook holds all of Find's state; FindNarrow and FindWide only lay it out. */
export function useFind() {
  const wide = useWide();
  const params = useLocalSearchParams<{ place?: string; lat?: string; lng?: string }>();
  const linked = parsePlaceParams(params);
  const [place, setPlace] = useState<Place>(linked ?? BUILT_IN_PLACES[0]);
  const [area, setArea] = useState<Bounds | null>(null);
  const [filters, setFilters] = useState<Filters>({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [text, setText] = useState('');
  const [region, setRegion] = useState<MapRegion | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  const choosePlace = useCallback((p: Place) => { setPlace(p); setArea(null); setRegion(null); setSelectedId(null); }, []);

  /* a link to another place while Find is open (state adjusted while rendering, not in an effect) */
  const linkKey = linked ? `${linked.name}|${linked.lat}|${linked.lng}` : '';
  const [seenKey, setSeenKey] = useState(linkKey);
  if (linkKey !== seenKey) {
    setSeenKey(linkKey);
    if (linked && !sameSpot(linked, place)) { choosePlace(linked); setText(''); }
  }

  /* the server filters and sorts; each answer remembers what it was asked, so the heading never describes the next search */
  const { gender, rent, kind } = filters;
  const areaKey = area ? JSON.stringify(area) : '';
  const res = useQuery(async () => {
    const f: Filters = { gender, rent, kind };
    const list = await ok(api.GET('/api/listings', { params: { query: buildListingsQuery({ place, area, filters: f }) } }));
    return { list, inArea: !!area, placeName: place.name, filtered: countFilters(f) > 0 };
  }, [place, areaKey, gender, rent, kind]);

  const answer = res.data;
  const list = useMemo(() => answer?.list ?? [], [answer]);
  const selected = list.find(p => p.id === selectedId);
  /* a new search that no longer has the selected PG drops the selection */
  if (answer && selectedId && !selected) setSelectedId(null);

  /* the person picked a place; on the wide website the address bar follows (setParams adds no history entry) */
  const pickPlace = useCallback((p: Place) => {
    choosePlace(p);
    if (wide) router.setParams(findHref(p).params);
  }, [choosePlace, wide]);

  const popular = usePopularPlaces();
  const nFilters = countFilters(filters);
  return {
    place, area, filters, setFilters, filtersOpen, nFilters, text, setText, selectedId, setSelectedId, setHoverId,
    res, answer, list, selected,
    mapSelectedId: hoverId ?? selectedId,
    offer: areaOffer(region, area),
    chips: placeChips(popular, BUILT_IN_PLACES, place),
    isChip: (c: Place) => samePlace(c, place),
    toggleFilters: () => setFiltersOpen(o => !o),
    clearFilters: () => setFilters({}),
    onRegion: setRegion,
    pickPlace,
    pickChip: (c: Place) => { setText(''); pickPlace(c); },
    searchArea: () => { if (region) setArea(roundBounds(region.bounds)); },
  };
}
export type FindModel = ReturnType<typeof useFind>;
