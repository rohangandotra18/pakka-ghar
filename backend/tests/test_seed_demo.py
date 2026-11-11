"""The development-only demo data command."""
from pathlib import Path
from urllib.parse import urlparse

import pytest
from django.core.management import call_command

from apps.core.rls import system
from apps.maintenance.models import TrustReport
from apps.property.models import Property
from apps.property.photos import km

from .conftest import Api, read, token_for


@pytest.fixture
def seeded(db, settings, tmp_path):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    call_command('seed_demo')
    return tmp_path


def in_box(x):
    return 30.55 <= x['lat'] <= 30.85 and 76.60 <= x['lng'] <= 77.00


def test_listings_near_pgimer_have_pins_rents_and_photos_on_disk(seeded):
    found = Api().get('/listings?lat=30.7649&lng=76.7757&radius_km=3').json()
    assert len(found) >= 5
    for x in found:
        assert in_box(x) and x['rent_paise'] > 0
        assert x['photos'], x['id']
        for ph in x['photos']:
            assert (seeded / urlparse(ph['url']).path.removeprefix('/media/')).exists()
            assert (seeded / urlparse(ph['thumb']).path.removeprefix('/media/')).exists()
        assert km(30.7649, 76.7757, x['lat'], x['lng']) <= 3


def test_every_city_has_listings_and_some_beds_are_taken(seeded):
    everything = Api().get('/listings').json()
    assert {x['city'] for x in everything} == {'chandigarh', 'mohali', 'panchkula'}
    assert len(everything) == 14 and all(in_box(x) for x in everything)
    assert any(x['free'] == 0 for x in everything) and sum(1 for x in everything if x['free']) >= 10
    assert any(x['rating'] for x in everything) and any(x['hot'] for x in everything)
    assert all(6000 <= x['rent_paise'] / 100 <= 18000 for x in everything)


def test_the_trust_team_sees_a_clean_and_an_incomplete_pg_and_two_reports(seeded):
    with system():
        from apps.core.models import Party
        staff = Party.objects.get(phone='+919000000001')
    queue = Api(token_for(staff)).get('/staff/queue')
    assert queue.status_code == 200
    q = queue.json()
    assert len(q['properties']) == 2 and len(q['reports']) == 2
    assert sorted(p['payout'] for p in q['properties']) == [False, True]
    assert all(p['pinned'] and p['no_cash_pledged'] and p['rooms'] for p in q['properties'])
    assert {r['category'] for r in q['reports']} == {'Asked to pay in cash', 'Listing issue'}
    assert read(lambda: TrustReport.objects.filter(status='open').count()) == 2


def test_running_it_twice_creates_nothing_new(seeded):
    before = read(lambda: Property.objects.count())
    assert before == 16
    call_command('seed_demo')
    assert read(lambda: Property.objects.count()) == before


def test_it_refuses_unless_debug_is_on(db, settings, tmp_path):
    settings.DEBUG = False
    settings.MEDIA_ROOT = tmp_path
    call_command('seed_demo')
    assert read(lambda: Property.objects.count()) == 0
    assert not list(Path(tmp_path).iterdir())
