#!/usr/bin/env python3
"""Fetch the places people search from (sectors, phases, colleges, hospitals, stations, bus stands, markets) for the
Chandigarh Tricity from OpenStreetMap and write backend/apps/property/data/tricity_places.json.

    python backend/scripts/fetch_places.py

Standard library only. Needs the network; it sends one Overpass request at a time with a pause between them and
retries with a growing wait when the server is busy. Then load the result with `manage.py load_places`.

The output is a derived extract of OpenStreetMap data, published under the Open Database Licence (ODbL) 1.0:
(c) OpenStreetMap contributors, https://www.openstreetmap.org/copyright

Which city a place is in. Chandigarh is the Union Territory's boundary (OSM admin_level 4). Mohali and Panchkula have
no city boundary in OSM, so each is the tehsil (admin_level 6) of that name: it covers the city without Zirakpur,
Kharar, Dera Bassi or Pinjore. A place inside none of the three, or inside more than one, is left out and counted.
"""
import json
import math
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINTS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
USER_AGENT = 'tricity-places-fetch/1.0'
BBOX = {'south': 30.55, 'west': 76.60, 'north': 30.85, 'east': 77.00}
PAUSE_S = 10          # between requests
TIMEOUT_S = 200       # per request
ATTEMPTS = 6          # per endpoint
OUT = Path(__file__).resolve().parent.parent / 'apps' / 'property' / 'data' / 'tricity_places.json'

# city -> (admin_level, exact OSM name or regex). Resolved on the server with map_to_area.
CITY_AREAS = {
    'chandigarh': ('4', '^Chandigarh$'),
    'panchkula': ('6', '^Panchkula$'),
    'mohali': ('6', r'^S\.?A\.?S\.? Nagar|^Sahibzada Ajit Singh Nagar|Mohali'),
}

SECTOR_NAME = r'^(Sector|Sec\.?|Phase|Ph\.?)[ -]?[0-9]+[ -]?[A-Za-z]?[0-9]?$'
BODY = f'''(
  nwr(area.a)["place"~"^(suburb|neighbourhood|quarter|locality|city_block)$"]["name"~"{SECTOR_NAME}"];
  nwr(area.a)["boundary"="administrative"]["admin_level"~"^(9|10|11)$"]["name"~"{SECTOR_NAME}"];
  nwr(area.a)["landuse"~"^(residential|commercial|retail|institutional)$"]["name"~"{SECTOR_NAME}"];
  nwr(area.a)["amenity"~"^(university|college)$"]["name"];
  nwr(area.a)["amenity"="hospital"]["name"];
  nwr(area.a)["railway"="station"]["name"];
  nwr(area.a)["amenity"="bus_station"]["name"];
  nwr(area.a)["amenity"="marketplace"]["name"];
  nwr(area.a)["shop"="mall"]["name"];
);
out center tags;'''

# The places shown before anyone types, in this order. Curated by hand, but only ever from fetched data:
#   osm      the OSM name to match (exact, ignoring case) in `city`; the script stops if it is not found
#   show     the name stored and shown (the OSM name is kept as a search alias)
#   also     other OSM names of the same institution in `city` (within 500 m): folded into this place as aliases
# The coordinates are always those of the matched OSM element.
CURATED = [
    {'rank': 1, 'city': 'chandigarh', 'osm': 'Postgraduate Institute of Medical Education and Research (PGIMER)', 'show': 'PGIMER',
     'also': ['PGI Chandigarh', 'PGI Emergency']},
    {'rank': 2, 'city': 'chandigarh', 'osm': 'Panjab University', 'show': 'Panjab University', 'also': []},
    {'rank': 3, 'city': 'chandigarh', 'osm': 'Sector 17', 'show': 'Sector 17', 'also': []},
    {'rank': 4, 'city': 'chandigarh', 'osm': 'Chandigarh Railway Station', 'show': 'Chandigarh Railway Station', 'also': []},
    {'rank': 5, 'city': 'chandigarh', 'osm': 'Chandigarh ISBT, Sector 43', 'show': 'ISBT Sector 43', 'also': []},
    {'rank': 6, 'city': 'chandigarh', 'osm': 'Chandigarh ISBT, Sector 17', 'show': 'ISBT Sector 17', 'also': []},
    {'rank': 7, 'city': 'chandigarh', 'osm': 'GMCH SECTOR 32', 'show': 'GMCH Sector 32', 'also': []},
    {'rank': 8, 'city': 'chandigarh', 'osm': 'Nexus Elante Mall', 'show': 'Nexus Elante Mall', 'also': []},
    {'rank': 9, 'city': 'chandigarh', 'osm': 'Chandigarh College of Architecture', 'show': 'Chandigarh College of Architecture', 'also': []},
    {'rank': 10, 'city': 'chandigarh', 'osm': 'Goswami Ganesh Dutta Sanatan Dharma College',
     'show': 'Goswami Ganesh Dutta Sanatan Dharma College', 'also': []},
    {'rank': 11, 'city': 'chandigarh', 'osm': 'Post Graduate Government College', 'show': 'Post Graduate Government College', 'also': []},
]
MERGE_WITHIN_M = 500

# `shop=mall` is often put on a single shop; a market or mall has to say so in its name.
MARKET_NAME = re.compile(r'market|mall|bazaar|bazar|mandi|plaza|square|elante|centra', re.I)
GENERIC_MARKETS = {'inner market', 'market', 'showrooms', 'shopping complex'}

SUBSECTOR = re.compile(r'^(?:Sector|Sec\.?|Phase|Ph\.?)[ -]?(\d+)[ -]?([A-Za-z]?\d?)$', re.I)


def ssl_context():
    ctx = ssl.create_default_context()
    if not ctx.get_ca_certs():   # some python.org builds on macOS ship without certificates
        for cafile in ('/etc/ssl/cert.pem', '/etc/ssl/certs/ca-certificates.crt'):
            if Path(cafile).exists():
                return ssl.create_default_context(cafile=cafile)
    return ctx


CTX = ssl_context()


def overpass(ql: str) -> dict:
    """One request at a time. Retries with a growing wait; falls back to a mirror."""
    last = None
    for url in ENDPOINTS:
        wait = 15
        for attempt in range(1, ATTEMPTS + 1):
            req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': ql}).encode(),
                                         headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=CTX) as r:
                    return json.loads(r.read())
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as e:
                last = e
                print(f'  {url} attempt {attempt}/{ATTEMPTS}: {e}; waiting {wait}s', file=sys.stderr)
                time.sleep(wait)
                wait = min(wait * 2, 120)
    raise SystemExit(f'Overpass could not be reached ({last}). Nothing was written.')


def city_query(city: str) -> str:
    level, name = CITY_AREAS[city]
    s, w, n, e = BBOX['south'], BBOX['west'], BBOX['north'], BBOX['east']
    name = name.replace('\\', '\\\\')
    return (f'[out:json][timeout:180];\nrel["boundary"="administrative"]["admin_level"="{level}"]["name"~"{name}"]'
            f'({s},{w},{n},{e});\nmap_to_area->.a;\n{BODY}')


def centre(el: dict):
    if 'center' in el:
        return el['center']['lat'], el['center']['lon']
    if 'lat' in el:
        return el['lat'], el['lon']
    return None


def classify(tags: dict) -> str | None:
    if SUBSECTOR.match(tags.get('name', '')) and (tags.get('place') or tags.get('boundary') == 'administrative' or tags.get('landuse')):
        return 'sector'
    a = tags.get('amenity')
    if a in ('university', 'college'):
        return 'college'
    if a == 'hospital':
        return 'hospital'
    if tags.get('railway') == 'station' or a == 'bus_station':
        return 'transit'
    if (a == 'marketplace' or tags.get('shop') == 'mall') and MARKET_NAME.search(tags.get('name', '')) \
            and tags.get('name', '').strip().lower() not in GENERIC_MARKETS:
        return 'market'
    return None


def significance(el: dict) -> int:
    t = el.get('tags', {})
    return ((3 if 'wikidata' in t else 0) + (3 if 'wikipedia' in t else 0) + {'relation': 2, 'way': 1}.get(el['type'], 0)
            + min(len(t), 20) // 5)


def aliases_of(tags: dict) -> list[str]:
    out = []
    for k in ('short_name', 'alt_name', 'official_name', 'old_name', 'name:en', 'int_name'):
        for v in re.split(r'[;]', tags.get(k, '')):
            v = v.strip()
            if v and v != tags.get('name'):
                out.append(v)
    return out


def normalise_sector(name: str):
    """`Sec-22` -> ('Sector 22', None); `sector 22 a` -> ('Sector 22', '22-A'); `Ph 7` -> ('Phase 7', None)."""
    m = SUBSECTOR.match(name.strip())
    word = 'Phase' if name.strip().lower().startswith('ph') else 'Sector'
    num, sub = m.group(1), m.group(2).upper()
    return f'{word} {num}', (f'{num}-{sub}' if sub else None)


def main():
    fetched, ambiguous = {}, set()   # (type, id) -> (city, element)
    queries = []
    for i, city in enumerate(CITY_AREAS):
        if i:
            time.sleep(PAUSE_S)
        ql = city_query(city)
        queries.append({'city': city, 'overpass_ql': ql})
        print(f'{city}: asking Overpass ...', file=sys.stderr)
        data = overpass(ql)
        els = data.get('elements', [])
        print(f'{city}: {len(els)} elements', file=sys.stderr)
        for el in els:
            key = (el['type'], el['id'])
            if key in fetched and fetched[key][0] != city:
                ambiguous.add(key)
            fetched[key] = (city, el)

    left_out = {'no_name_or_kind': 0, 'no_position': 0, 'in_two_cities': len(ambiguous)}
    best: dict[tuple[str, str], tuple[int, dict]] = {}
    subs: dict[tuple[str, str], list[tuple[str, int, dict]]] = {}   # (parent, city) -> [(sub-sector label, score, record)]

    def keep(name, city, score, rec):
        if (name, city) not in best or score > best[(name, city)][0]:
            best[(name, city)] = (score, rec)

    for key, (city, el) in fetched.items():
        if key in ambiguous:
            continue
        tags = el.get('tags', {})
        kind, pos = classify(tags), centre(el)
        if not kind or not tags.get('name'):
            left_out['no_name_or_kind'] += 1
            continue
        if not pos:
            left_out['no_position'] += 1
            continue
        name = tags['name'].strip()
        rec = {**el, '_pos': pos, '_kind': kind, '_aliases': aliases_of(tags)}
        if kind == 'sector':
            name, sub = normalise_sector(name)
            if sub:
                subs.setdefault((name, city), []).append((sub, significance(el), rec))
                continue
        keep(name, city, significance(el), rec)
    for (parent, city), found in subs.items():
        if (parent, city) in best:   # 22-A is another way to say Sector 22
            continue
        for sub, score, rec in found:   # no parent in the data: the sub-sector stands on its own
            keep(f"{parent.split(' ')[0]} {sub}", city, score, rec)

    places = []
    for (name, city), (score, rec) in best.items():
        al = list(rec['_aliases']) + [sub for sub, _, _ in subs.get((name, city), [])]
        lat, lng = rec['_pos']
        places.append({'name': name[:120], 'kind': rec['_kind'], 'city': city, 'lat': round(lat, 6), 'lng': round(lng, 6),
                       'aliases': ' '.join(dict.fromkeys(a.replace(',', ' ') for a in al)), 'popular_rank': None, 'source': 'osm',
                       '_score': score, '_wiki': 'wikidata' in rec['tags'] or 'wikipedia' in rec['tags']})
    apply_curated(places)
    for p in places:
        p.pop('_score'), p.pop('_wiki')
    places.sort(key=lambda p: (p['city'], p['kind'], natural(p['name'])))

    counts = {}
    for p in places:
        counts.setdefault(p['kind'], {}).setdefault(p['city'], 0)
        counts[p['kind']][p['city']] += 1
    doc = {
        'metadata': {
            'source': '© OpenStreetMap contributors, ODbL 1.0',
            'licence': 'This file is a derived extract of OpenStreetMap data and is published under the Open Database '
                       'Licence (ODbL) 1.0. https://www.openstreetmap.org/copyright',
            'fetched_on': datetime.now(timezone.utc).date().isoformat(),
            'bbox': BBOX,
            'endpoint': 'Overpass API',
            'city_rule': 'chandigarh: OSM admin boundary level 4 "Chandigarh"; panchkula and mohali: the level 6 (tehsil) '
                         'boundary of that name. Places outside all three, or inside more than one, are left out.',
            'queries': queries,
            'counts': counts,
            'left_out': left_out,
        },
        'places': places,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + '\n')
    print(f'wrote {len(places)} places to {OUT}', file=sys.stderr)
    print(json.dumps({'counts': counts, 'left_out': left_out}, indent=1))


def natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def metres(a: dict, b: dict) -> float:
    r = 3.141592653589793 / 180
    dlat, dlng = (b['lat'] - a['lat']) * r, (b['lng'] - a['lng']) * r
    h = math.sin(dlat / 2) ** 2 + math.cos(a['lat'] * r) * math.cos(b['lat'] * r) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def apply_curated(places: list[dict]) -> None:
    """Rank, rename and merge the curated places. Stops loudly if the fetched data does not hold one."""
    for c in CURATED:
        def find(osm):
            hits = [p for p in places if p['city'] == c['city'] and p['name'].lower() == osm.lower()]
            if not hits:
                raise SystemExit(f"Curated place {osm!r} ({c['city']}) is not in the fetched data. Nothing was written.")
            return hits[0]
        p = find(c['osm'])
        for other in c['also']:
            dup = find(other)
            if metres(p, dup) > MERGE_WITHIN_M:
                raise SystemExit(f"{other!r} is {metres(p, dup):.0f} m from {c['osm']!r}: not the same place. Nothing was written.")
            p['aliases'] = ' '.join(dict.fromkeys(x for x in [p['aliases'], dup['name'].replace(',', ' '), dup['aliases']] if x))
            places.remove(dup)
        p['popular_rank'] = c['rank']
        if p['name'] != c['show']:
            p['aliases'] = ' '.join(dict.fromkeys(x for x in [p['name'].replace(',', ' '), p['aliases']] if x))
            p['name'] = c['show']


if __name__ == '__main__':
    main()
