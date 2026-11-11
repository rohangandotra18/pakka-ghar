/* Run with `node src/features/search/findState.test.mjs` (plain node, no framework). */
import assert from 'node:assert/strict';
import { RADIUS_KM, areaOffer, bboxString, bboxTooLarge, boundsDiffer, buildListingsQuery, countFilters, placeChips, placeSubtitle, round5, roundBounds } from './findState.js';

const pgimer = { name: 'PGIMER', lat: 30.7649, lng: 76.7757 };
const box = { west: 76.7, south: 30.7, east: 76.8, north: 30.8 };

/* place mode: lat/lng + radius, never bbox */
assert.deepEqual(buildListingsQuery({ place: pgimer, area: null, filters: {} }), { lat: 30.7649, lng: 76.7757, radius_km: RADIUS_KM });
assert.deepEqual(
  buildListingsQuery({ place: pgimer, area: null, filters: { gender: 'Girls', rent: 10000, kind: 'double' } }),
  { lat: 30.7649, lng: 76.7757, radius_km: 3, gender: 'Girls', max_rent_paise: 1000000, kind: 'double' });
/* area mode: bbox only, no lat/lng/radius, filters still apply */
const area = buildListingsQuery({ place: pgimer, area: box, filters: { rent: 8000 } });
assert.deepEqual(area, { bbox: '76.7,30.7,76.8,30.8', max_rent_paise: 800000 });
assert.ok(!('lat' in area) && !('lng' in area) && !('radius_km' in area));

/* rounding */
assert.equal(round5(76.123456789), 76.12346);
assert.equal(bboxString({ west: 76.7000049, south: 30.7000051, east: 76.8, north: 30.81234567 }), '76.7,30.70001,76.8,30.81235');
assert.deepEqual(roundBounds({ west: 1.000004, south: 2, east: 3, north: 4 }).west, 1);

/* larger than 1 degree is rejected, exactly 1 is fine */
assert.equal(bboxTooLarge(box), false);
assert.equal(bboxTooLarge({ west: 76, south: 30.7, east: 77, north: 31.7 }), false);
assert.equal(bboxTooLarge({ west: 76, south: 30.7, east: 77.01, north: 30.8 }), true);
assert.equal(bboxTooLarge({ west: 76, south: 30, east: 76.5, north: 31.2 }), true);

/* differs from the searched area */
assert.equal(boundsDiffer(box, null), true);
assert.equal(boundsDiffer(box, { ...box }), false);
assert.equal(boundsDiffer(box, { ...box, west: 76.700001 }), false);   // same once rounded
assert.equal(boundsDiffer(box, { ...box, west: 76.69 }), true);

/* the pill */
assert.equal(areaOffer(null, null), 'none');
assert.equal(areaOffer({ bounds: box, byUser: false }, null), 'none');   // the map moved itself
assert.equal(areaOffer({ bounds: box, byUser: true }, null), 'search');   // place mode, person panned
assert.equal(areaOffer({ bounds: box, byUser: true }, { ...box }), 'none');   // already searched this area
assert.equal(areaOffer({ bounds: box, byUser: true }, { ...box, east: 76.9 }), 'search');
assert.equal(areaOffer({ bounds: { west: 70, south: 20, east: 80, north: 30 }, byUser: true }, null), 'zoom');
assert.equal(areaOffer({ bounds: { west: 70, south: 20, east: 80, north: 30 }, byUser: false }, null), 'none');

/* filters */
assert.equal(countFilters({}), 0);
assert.equal(countFilters({ gender: 'Boys', kind: 'single' }), 2);

/* place wording */
assert.equal(placeSubtitle({ kind: 'sector', city: 'chandigarh' }), 'Sector · Chandigarh');
assert.equal(placeSubtitle({ kind: 'college', city: 'mohali' }), 'College · Mohali');
assert.equal(placeSubtitle({ kind: 'transit', city: 'panchkula' }), 'Station · Panchkula');
assert.equal(placeSubtitle({ kind: 'park', city: 'mohali' }), 'Park · Mohali');

/* chips */
const fallback = [pgimer, { name: 'Panjab University', lat: 1, lng: 2 }];
const sec22 = { name: 'Sector 22', lat: 30.73, lng: 76.77 };
assert.deepEqual(placeChips(undefined, fallback, pgimer), fallback);
assert.deepEqual(placeChips([], fallback, sec22), [sec22, ...fallback]);
const many = Array.from({ length: 11 }, (_, i) => ({ name: 'P' + i, lat: i, lng: i }));
assert.equal(placeChips(many, fallback, many[0]).length, 6);
assert.equal(placeChips(many, fallback, many[9]).length, 7);   // a searched place that isn't a chip goes in front
assert.equal(placeChips(many, fallback, { ...many[1], name: 'p1' })[0].name, 'P0');   // matched by name, any case

console.log('findState: ok');
