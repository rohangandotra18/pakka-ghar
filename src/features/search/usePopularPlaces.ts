import { useMemo } from 'react';
import { api, ok, useQuery } from '@/core/api';
import type { Place } from './findState';

/* Places people search from until the server's list arrives (or if it can't be reached). */
export const BUILT_IN_PLACES: Place[] = [
  { name: 'PGIMER', lat: 30.7649, lng: 76.7757 },
  { name: 'Panjab University', lat: 30.7605, lng: 76.766 },
  { name: 'Sector 17', lat: 30.7412, lng: 76.7788 },
];

/* The popular places from GET /api/places; the three built-in ones while it loads, fails or is empty.
     const places = usePopularPlaces();
     places.map(p => <Chip key={p.name} label={p.name} onPress={() => router.push(findHref(p))} />) */
export function usePopularPlaces(): Place[] {
  const res = useQuery(() => ok(api.GET('/api/places')), []);
  return useMemo(() => {
    const served = res.data?.map(p => ({ name: p.name, lat: p.lat, lng: p.lng }));
    return served && served.length ? served : BUILT_IN_PLACES;
  }, [res.data]);
}
