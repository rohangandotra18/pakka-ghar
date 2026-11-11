"""Find screen search: PGs in a map area, room filters, and the list of places people jump the map to."""
import json
from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.rls import system
from apps.property.models import Bed, Place, Property

from .conftest import Api
from .factories import make_property, org_with_owner, person, stay

BOX = '76.76,30.74,76.78,30.76'          # holds both PGs of the `world`
EAST = '76.79,30.71,76.81,30.73'         # an empty patch of map for PGs these tests add


def pg(slug, lat, lng, rooms, status='published', name=None):
    """A published PG at a point, with `rooms` like [('101', 'double', 9000)]."""
    with system():
        o = org_with_owner(f'Owner of {slug}', person(f'Owner {slug}'))
        return make_property(o, slug, name or slug.title(), 'Boys', 'Sector 15', 'x', 'chandigarh', lat, lng, '3 meals', rooms, status)


def fill(prop, room):
    """Every bed of a room let for the coming month."""
    with system():
        for b in Bed.objects.filter(room__property=prop, room__number=room):
            stay(b, person(f'Resident {prop.slug}{room}{b.label}'), date(2026, 3, 1))


def ids(r):
    assert r.status_code == 200, r.content
    return [x['id'] for x in r.json()]


# ---- the map area ---------------------------------------------------------------------------------------

def test_bbox_returns_only_pgs_inside_the_box(world):
    pg('far', 30.70, 76.72, [('1', 'single', 5000)])
    assert sorted(ids(Api().get(f'/listings?bbox={BOX}'))) == ['gurnoor', 'sidhu']
    assert ids(Api().get('/listings?bbox=76.74,30.70,76.74001,30.70001')) == []
    assert ids(Api().get('/listings?bbox=76.715,30.695,76.725,30.705')) == ['far']


def test_bbox_ignores_the_radius_and_a_point_only_orders_and_measures(world):
    r = Api().get(f'/listings?bbox={BOX}&lat=30.7543&lng=76.7713&radius_km=0.1')
    assert ids(r) == ['sidhu', 'gurnoor']                    # gurnoor is ~0.5 km away: beyond the radius, still shown
    assert r.json()[0]['km'] == 0.1 and r.json()[1]['km'] > 0.3
    assert ids(Api().get(f'/listings?bbox={BOX}&lat=30.7509&lng=76.7740')) == ['gurnoor', 'sidhu']
    assert {x['km'] for x in Api().get(f'/listings?bbox={BOX}').json()} == {None}


@pytest.mark.parametrize('bbox', [
    '', 'a,b,c,d', '76.7,30.7,76.8', '76.7,30.7,76.8,30.8,1', '76.8,30.7,76.7,30.8', '76.7,30.8,76.8,30.7',
    '76.7,30.7,76.7,30.8', '76,30,77.5,30.5', '76,30,76.5,31.5', '170,0,181,0.5', '0,89.5,0.5,91', 'nan,30,76.5,30.5',
    '76,30,inf,30.5', '76,30,1e999,30.5'])
def test_a_bad_bbox_is_a_clear_422(world, bbox):
    r = Api().get(f'/listings?bbox={bbox}')
    assert r.status_code == 422, bbox
    assert r.json()['code'] == 'bad_bbox'


def test_a_box_of_exactly_one_degree_is_allowed(world):
    assert Api().get('/listings?bbox=76.5,30.3,77.5,31.3').status_code == 200


def test_unpublished_pgs_never_appear_in_an_area_search(world):
    for status in ('draft', 'submitted', 'paused'):
        pg(f'hidden-{status}', 30.72, 76.80, [('1', 'single', 5000)], status=status)
    pg('shown', 30.72, 76.801, [('1', 'single', 5000)])
    assert ids(Api().get(f'/listings?bbox={EAST}')) == ['shown']


# ---- filters --------------------------------------------------------------------------------------------

def test_max_rent_and_kind_keep_pgs_with_a_free_bed_in_a_matching_room(world):
    api = Api()
    assert sorted(ids(api.get(f'/listings?bbox={BOX}&max_rent_paise=950000'))) == ['sidhu']      # 9000 and 10000
    assert sorted(ids(api.get(f'/listings?bbox={BOX}&max_rent_paise=1000000'))) == ['gurnoor', 'sidhu']
    assert ids(api.get(f'/listings?bbox={BOX}&max_rent_paise=800000')) == []
    assert sorted(ids(api.get(f'/listings?bbox={BOX}&kind=triple'))) == ['gurnoor', 'sidhu']
    assert ids(api.get(f'/listings?bbox={BOX}&kind=double')) == ['sidhu']
    assert ids(api.get(f'/listings?bbox={BOX}&kind=single')) == []
    # both conditions must hold in the same room
    assert ids(api.get(f'/listings?bbox={BOX}&kind=triple&max_rent_paise=950000')) == ['sidhu']
    assert ids(api.get(f'/listings?bbox={BOX}&kind=single&max_rent_paise=99999999')) == []
    two = pg('mixed', 30.72, 76.80, [('1', 'single', 15000), ('2', 'double', 6000)])
    assert ids(api.get(f'/listings?bbox={EAST}&kind=single&max_rent_paise=1000000')) == []      # single is dear, double is cheap
    assert ids(api.get(f'/listings?bbox={EAST}&kind=double&max_rent_paise=1000000')) == [two.slug]


def test_filters_also_work_around_a_point(world):
    assert ids(Api().get('/listings?lat=30.7543&lng=76.7713&kind=double')) == ['sidhu']


def test_free_only_drops_full_pgs(world):
    fill(world['b'], '204')
    api = Api()
    assert sorted(ids(api.get(f'/listings?bbox={BOX}'))) == ['gurnoor', 'sidhu']                # full, but still listed
    assert ids(api.get(f'/listings?bbox={BOX}&free_only=true')) == ['sidhu']
    assert ids(api.get(f'/listings?bbox={BOX}&free_only=false')) != ids(api.get(f'/listings?bbox={BOX}&free_only=true'))


def test_a_pg_whose_only_matching_room_is_full_is_excluded(world):
    p = pg('twin', 30.72, 76.80, [('1', 'single', 5000), ('2', 'double', 9000)])
    fill(p, '1')
    api = Api()
    assert ids(api.get(f'/listings?bbox={EAST}&free_only=true')) == ['twin']                      # the double is free
    assert ids(api.get(f'/listings?bbox={EAST}&kind=single')) == []
    assert ids(api.get(f'/listings?bbox={EAST}&max_rent_paise=600000')) == []                    # only the full single is that cheap
    assert ids(api.get(f'/listings?bbox={EAST}&kind=double')) == ['twin']


def test_the_card_shows_the_cheapest_matching_room_with_a_free_bed(world):
    p = pg('priced', 30.72, 76.80, [('1', 'double', 12000), ('2', 'double', 8000), ('3', 'single', 7000)])
    api = Api()
    rent = lambda qs: api.get(f'/listings?bbox={EAST}{qs}').json()[0]['rent_paise']             # noqa: E731
    assert rent('') == 1200000                      # unchanged: the first free bed's room
    assert rent('&max_rent_paise=1500000') == 700000                    # cheapest room with a free bed, the single
    assert rent('&kind=double') == 800000
    assert rent('&kind=double&max_rent_paise=1000000') == 800000
    assert rent('&kind=double&max_rent_paise=1250000') == 800000
    fill(p, '2')                                    # the cheap double is full: it no longer sets the price
    assert rent('&kind=double') == 1200000
    assert rent('&max_rent_paise=1500000') == 700000
    fill(p, '3')
    assert rent('&max_rent_paise=1500000') == 1200000
    assert rent('') == 1200000


@pytest.mark.parametrize('qs', ['max_rent_paise=0', 'max_rent_paise=-5', 'kind=quad', 'kind=', 'limit=0', 'limit=201', 'limit=-1'])
def test_bad_filters_are_a_clear_422(world, qs):
    r = Api().get(f'/listings?bbox={BOX}&{qs}')
    assert r.status_code == 422 and r.json()['code'] == 'bad_filter', qs


# ---- order and limit ------------------------------------------------------------------------------------

def test_without_a_point_free_pgs_come_first_then_cheaper_then_by_name(world):
    pg('full', 30.72, 76.80, [('1', 'single', 3000)])
    pg('dear', 30.72, 76.801, [('1', 'single', 9000)])
    pg('b-cheap', 30.72, 76.802, [('1', 'single', 6000)], name='B Cheap')
    pg('a-cheap', 30.72, 76.803, [('1', 'single', 6000)], name='A Cheap')
    fill(_get('full'), '1')
    assert ids(Api().get(f'/listings?bbox={EAST}')) == ['a-cheap', 'b-cheap', 'dear', 'full']


def _get(slug):
    with system():
        return Property.objects.get(slug=slug)


def test_with_a_point_nearest_comes_first(world):
    pg('nearer', 30.7590, 76.7713, [('1', 'single', 99000)])
    assert ids(Api().get('/listings?lat=30.7600&lng=76.7713'))[:2] == ['nearer', 'sidhu']


def test_limit_caps_the_results_after_sorting(world):
    api = Api()
    assert len(ids(api.get(f'/listings?bbox={BOX}&limit=1'))) == 1
    assert ids(api.get(f'/listings?bbox={BOX}&lat=30.7509&lng=76.7740&limit=1')) == ['gurnoor']
    assert len(ids(api.get(f'/listings?bbox={BOX}&limit=200'))) == 2
    for n in (1, 200):
        assert Api().get(f'/listings?limit={n}').status_code == 200


def test_existing_parameters_still_work(world):
    api = Api()
    assert ids(api.get('/listings?lat=30.7543&lng=76.7713&radius_km=0.3')) == ['sidhu']
    assert ids(api.get('/listings?gender=Girls')) == ['gurnoor']
    assert ids(api.get('/listings?q=gurnoor')) == ['gurnoor']
    assert ids(api.get(f'/listings?bbox={BOX}&gender=Boys')) == ['sidhu']


def test_an_area_search_costs_the_same_however_many_pgs_match(db):
    def count(n):
        with CaptureQueriesContext(connection) as ctx:
            assert len(Api().get(f'/listings?bbox={EAST}&max_rent_paise=1000000&kind=single').json()) == n
        return len(ctx.captured_queries)
    for i in range(2):
        pg(f'few-{i}', 30.72, 76.80 + i * 0.001, [('1', 'single', 5000), ('2', 'double', 6000)])
    few = count(2)
    for i in range(2, 8):
        pg(f'few-{i}', 30.72, 76.80 + i * 0.001, [('1', 'single', 5000), ('2', 'double', 6000)])
    assert count(8) == few <= 20


# ---- places ---------------------------------------------------------------------------------------------

@pytest.fixture
def places(db):
    rows = [   # name, kind, city, lat, lng, aliases, popular_rank
        ('Sector 22', 'sector', 'chandigarh', 30.7333, 76.7794, '22-A 22-B', None),
        ('Sector 220', 'sector', 'mohali', 30.66, 76.70, '', None),
        ('Sector 2', 'sector', 'chandigarh', 30.7800, 76.8000, '', None),
        ('Sector 17', 'sector', 'chandigarh', 30.7412, 76.7788, '', 3),
        ('ISBT Sector 17', 'transit', 'chandigarh', 30.7357, 76.7790, 'Chandigarh ISBT', 6),
        ('Aqua Sector 17 Market', 'market', 'chandigarh', 30.7410, 76.7780, '', None),
        ('Sector 22 Market', 'market', 'chandigarh', 30.7340, 76.7800, '', None),
        ('Government College Sector 22', 'college', 'chandigarh', 30.7350, 76.7790, '', 9),
        ('Phase 7', 'sector', 'mohali', 30.7100, 76.7200, '', None),
        ('Phase 70', 'sector', 'mohali', 30.7500, 76.7100, '', None),
        ('PGIMER', 'hospital', 'chandigarh', 30.7649, 76.7757, 'Postgraduate Institute of Medical Education and Research (PGIMER) PGI Chandigarh', 1),
        ('PGI Dispensary', 'hospital', 'chandigarh', 30.7000, 76.7000, '', None),
        ('Panjab University', 'college', 'chandigarh', 30.7605, 76.7660, '', 2),
        ('Fortis Hospital', 'hospital', 'mohali', 30.6900, 76.7300, 'Fortis Mohali', None),
        ('Zeta Annex', 'landmark', 'mohali', 30.70, 76.70, '', 4),
        ('Alpha Annex', 'landmark', 'mohali', 30.70, 76.71, '', 5),
        ('Beta Annex', 'landmark', 'mohali', 30.70, 76.72, '', None),
    ]
    for name, kind, city, lat, lng, aliases, rank in rows:
        Place.objects.create(name=name, kind=kind, city=city, lat=lat, lng=lng, aliases=aliases, popular_rank=rank)


def found(q, **kw):
    qs = '&'.join([f'q={q}'] + [f'{k}={v}' for k, v in kw.items()])
    r = Api().get(f'/places?{qs}')
    assert r.status_code == 200, r.content
    return [x['name'] for x in r.json()]


def test_places_are_readable_without_signing_in_and_have_floats(places):
    r = Api().get('/places?q=pgimer')
    assert r.status_code == 200
    assert r.json()[0] == {'id': r.json()[0]['id'], 'name': 'PGIMER', 'kind': 'hospital', 'city': 'chandigarh', 'lat': 30.7649, 'lng': 76.7757}


def test_the_web_role_can_read_places_in_a_real_request(places):
    with connection.cursor() as c:
        c.execute("SELECT current_user, has_table_privilege(current_user, 'property_place', 'SELECT')")
        user, can = c.fetchone()
    assert user == 'pakka' and can
    assert found('sector 17')[0] == 'Sector 17'


def test_without_a_query_the_ranked_places_in_rank_order(places):
    # rank 1 first, whatever the alphabet says; unranked places never appear
    r = [x['name'] for x in Api().get('/places').json()]
    assert r == ['PGIMER', 'Panjab University', 'Sector 17', 'Zeta Annex', 'Alpha Annex', 'ISBT Sector 17', 'Government College Sector 22']
    assert found('', limit=3) == r[:3]


def test_ranked_places_come_before_unranked_ones_at_the_same_match_level(places):
    assert found('annex') == ['Zeta Annex', 'Alpha Annex', 'Beta Annex']       # by rank, then unranked
    # `Aqua Sector 17 Market` sorts first alphabetically but is unranked; both only contain the query
    assert found('17') == ['Sector 17', 'ISBT Sector 17', 'Aqua Sector 17 Market']
    assert found('pgi')[:2] == ['PGIMER', 'PGI Dispensary']                    # PGIMER starts with it and is ranked; the alias holds the long name
    assert found('postgraduate institute') == ['PGIMER']                       # the long OSM name still finds it


def test_digits_alone_find_that_sector_first(places):
    assert found('22')[0] == 'Sector 22'
    assert 'Sector 220' not in found('22')           # 22 is a whole number, not the start of 220
    assert found('22')[1:] == ['Sector 22 Market', 'Government College Sector 22']
    assert found('220') == ['Sector 220']
    assert found('7') == ['Phase 7']


def test_the_ways_people_type_a_sector_or_phase(places):
    for q in ('sector 22', 'sec 22', 'Sec22', 'SECTOR22', 'sector%2022'):
        assert found(q)[0] == 'Sector 22', q
    for q in ('phase 7', 'ph 7', 'Ph7', 'PHASE%207'):
        assert found(q) == ['Phase 7'], q


def test_names_that_start_with_the_query_come_before_names_that_contain_it(places):
    r = found('sector 22')
    assert r == ['Sector 22', 'Sector 22 Market', 'Government College Sector 22']      # the popular college is last
    assert found('sec')[:2] == ['Sector 17', 'Sector 2'] or found('sec')[0] == 'Sector 17'
    assert found('pgi')[0] == 'PGIMER'
    assert found('uni') == ['Panjab University']


def test_aliases_and_case_and_every_word_must_match(places):
    assert found('institute') == ['PGIMER']
    assert found('PANJAB') == ['Panjab University']
    assert found('fortis mohali') == ['Fortis Hospital']
    assert found('fortis') == ['Fortis Hospital']
    assert found('college panjab') == []                             # words must all match
    assert found('22-a') == ['Sector 22']


def test_places_limit_and_validation(places):
    assert len(found('sector', limit=3)) == 3
    assert len(found('sector')) <= 8
    assert Api().get('/places?limit=0').status_code == 422
    assert Api().get('/places?limit=21').json()['code'] == 'bad_filter'
    assert Api().get('/places?limit=20').status_code == 200
    assert found('x' * 500) == []                                    # a long query is trimmed, not an error
    assert Api().get('/places?q=%20%20').status_code == 200


# ---- load_places ----------------------------------------------------------------------------------------

def test_load_places_is_idempotent_and_updates(db, tmp_path):
    f = tmp_path / 'places.json'
    doc = {'metadata': {}, 'places': [
        {'name': 'Sector 9', 'kind': 'sector', 'city': 'chandigarh', 'lat': 30.75, 'lng': 76.79, 'aliases': '', 'popular_rank': None, 'source': 'osm'},
        {'name': 'Sector 9', 'kind': 'sector', 'city': 'panchkula', 'lat': 30.69, 'lng': 76.85, 'aliases': '9-A', 'popular_rank': 4, 'source': 'osm'}]}
    f.write_text(json.dumps(doc))
    call_command('load_places', str(f))
    call_command('load_places', str(f))
    assert Place.objects.count() == 2
    doc['places'][0].update(lat=30.76, popular_rank=2)
    f.write_text(json.dumps(doc))
    call_command('load_places', str(f))
    p = Place.objects.get(name='Sector 9', city='chandigarh')
    assert Place.objects.count() == 2 and float(p.lat) == 30.76 and p.popular_rank == 2


def test_load_places_removes_osm_rows_that_left_the_file_but_keeps_other_sources(db, tmp_path):
    f = tmp_path / 'places.json'
    row = lambda n, rank=None: {'name': n, 'kind': 'sector', 'city': 'chandigarh', 'lat': 30.75, 'lng': 76.79, 'aliases': '', 'popular_rank': rank, 'source': 'osm'}  # noqa: E731
    f.write_text(json.dumps({'places': [row('Sector 1'), row('PGI Chandigarh', 1), row('Sector 3')]}))
    call_command('load_places', str(f))
    Place.objects.create(name='Hand added', kind='landmark', city='mohali', lat=30.7, lng=76.7, source='app')
    f.write_text(json.dumps({'places': [row('Sector 1'), row('Sector 3', 1)]}))
    out = StringIO()
    call_command('load_places', str(f), stdout=out)
    assert set(Place.objects.values_list('name', flat=True)) == {'Sector 1', 'Sector 3', 'Hand added'}
    assert '1 removed' in out.getvalue()
    assert Place.objects.get(name='Sector 3').popular_rank == 1
    f.write_text(json.dumps({'places': [row('Sector 1'), row('Sector 3')]}))    # rank dropped from the file: dropped in the table
    call_command('load_places', str(f))
    assert Place.objects.get(name='Sector 3').popular_rank is None


def test_the_shipped_places_file_loads(db):
    """Shape check only: the contents come from the fetch and are not asserted on."""
    call_command('load_places')
    assert Place.objects.exists()
    assert all(p.source for p in Place.objects.all()[:5])
