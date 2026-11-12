/* The rules behind Find that need no React: what to ask the API in each search mode, the map-area limits, and the
   wording for places. Kept in plain JavaScript (with findState.d.ts) so `node src/features/search/findState.test.mjs` can run it. */

export const RADIUS_KM = 3;
/* the API rejects a bbox with a side longer than this many degrees */
export const MAX_BBOX_SPAN = 1;

const KIND_LABEL = { sector: 'Sector', college: 'College', hospital: 'Hospital', market: 'Market', transit: 'Station', landmark: 'Landmark' };
const titleCase = s => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '');

export const round5 = n => Math.round(n * 1e5) / 1e5;

export function roundBounds(b) {
  return { west: round5(b.west), south: round5(b.south), east: round5(b.east), north: round5(b.north) };
}

export function bboxString(b) {
  const r = roundBounds(b);
  return `${r.west},${r.south},${r.east},${r.north}`;
}

export function bboxTooLarge(b) {
  const r = roundBounds(b);
  return r.east - r.west > MAX_BBOX_SPAN || r.north - r.south > MAX_BBOX_SPAN;
}

/* true unless both areas are the same once rounded to what the API receives */
export function boundsDiffer(a, b) {
  if (!a || !b) return true;
  return bboxString(a) !== bboxString(b);
}

/* The listings request: around the chosen place (place mode) or inside the map's box (area mode), plus filters. */
export function buildListingsQuery({ place, area, filters }) {
  const q = {};
  if (area) q.bbox = bboxString(area);
  else { q.lat = place.lat; q.lng = place.lng; q.radius_km = RADIUS_KM; }
  if (filters.gender) q.gender = filters.gender;
  if (filters.rent) q.max_rent_paise = Math.round(filters.rent * 100);
  if (filters.kind) q.kind = filters.kind;
  return q;
}

export const countFilters = f => (f.gender ? 1 : 0) + (f.rent ? 1 : 0) + (f.kind ? 1 : 0);

/* What the "Search this area" pill should do after the map comes to rest: nothing, search, or ask to zoom in. */
export function areaOffer(region, searched) {
  if (!region || !region.byUser || !boundsDiffer(region.bounds, searched)) return 'none';
  return bboxTooLarge(region.bounds) ? 'zoom' : 'search';
}

/* "Sector · Chandigarh" */
export function placeSubtitle(p) {
  return `${KIND_LABEL[p.kind] ?? titleCase(p.kind)} · ${titleCase(p.city)}`;
}

export const samePlace = (a, b) => a.name.trim().toLowerCase() === b.name.trim().toLowerCase();

/* The popular-place chips: up to `max` from the server (or the built-in few until it answers), with a place chosen from
   search put first when it isn't among them. */
export function placeChips(popular, fallback, chosen, max = 6) {
  const base = (popular && popular.length ? popular : fallback).slice(0, max);
  return base.some(p => samePlace(p, chosen)) ? base : [chosen, ...base];
}

/* The Tricity, as a box: a link naming a place outside it is ignored. */
const TRICITY = { south: 30.55, north: 30.85, west: 76.6, east: 77.0 };
const round6 = n => Math.round(n * 1e6) / 1e6;

function coordinate(v, min, max) {
  if (typeof v !== 'string' || !v.trim()) return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= min && n <= max ? n : null;
}

/* A place from the address (`/find?place=Sector%2022&lat=30.733044&lng=76.771339`), or null when any part is missing or
   invalid: the name must be 1 to 80 characters, and lat/lng numbers inside the Tricity. */
export function parsePlaceParams(params) {
  if (!params) return null;
  const name = typeof params.place === 'string' ? params.place.trim() : '';
  const lat = coordinate(params.lat, TRICITY.south, TRICITY.north);
  const lng = coordinate(params.lng, TRICITY.west, TRICITY.east);
  if (name.length < 1 || name.length > 80 || lat === null || lng === null) return null;
  return { name, lat, lng };
}

/* The link that opens Find on a place (the inverse of parsePlaceParams): router.push(findHref(place)) */
export function findHref(place) {
  return { pathname: '/find', params: { place: place.name, lat: round6(place.lat), lng: round6(place.lng) } };
}

/* true when both are the same spot, once rounded as the address rounds it */
export const sameSpot = (a, b) => samePlace(a, b) && round6(a.lat) === round6(b.lat) && round6(a.lng) === round6(b.lng);
