import { api, ok, useQuery } from '@/core/api';

/* The two lists the desktop landing page shows. Each is `undefined` while loading and while the request has failed, and
   `failed` says which, so a failure just leaves that part of the page out. */

/* every published PG, for the map (the server's largest page is 200) */
export const MAP_LIMIT = 200;
export function useMapListings() {
  const res = useQuery(() => ok(api.GET('/api/listings', { params: { query: { limit: MAP_LIMIT } } })), []);
  return { list: res.data, failed: !!res.error && !res.data };
}

/* up to six PGs with a bed free now, for the cards */
export function useFreeListings() {
  const res = useQuery(() => ok(api.GET('/api/listings', { params: { query: { free_only: true, limit: 6 } } })), []);
  return { list: res.data, failed: !!res.error && !res.data };
}
