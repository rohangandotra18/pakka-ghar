"""Sealed offers: listed rent to +15%, owners see names and records, tenants see only where they stand."""
from datetime import date, timedelta

from django.utils import timezone

from apps.booking.models import Booking, Offer
from apps.booking.services import open_offers
from .factories import rate, stay
from apps.core.rls import system

from .conftest import read
from .helpers import bed


def _open(world):
    with system():
        return open_offers(bed(world['a'], '104', 3))


def test_offer_must_sit_between_listed_rent_and_cap(world):
    _open(world)
    api = world['api'](world['simran'])
    assert api.post('/offers', {'listing': 'sidhu', 'amount_paise': 899900, 'months': 11}).status_code == 422
    assert api.post('/offers', {'listing': 'sidhu', 'amount_paise': 1040000, 'months': 11}).status_code == 422  # cap is ₹10,350
    ok = api.post('/offers', {'listing': 'sidhu', 'amount_paise': 1035000, 'months': 11})
    assert ok.status_code == 200 and ok.json()['cap_paise'] == 1035000
    assert api.post('/offers', {'listing': 'sidhu', 'amount_paise': 950000, 'months': 7}).status_code == 422


def test_sealed_round_tenant_sees_standing_owner_sees_people(world):
    _open(world)
    world['api'](world['aman']).post('/offers', {'listing': 'sidhu', 'amount_paise': 1020000, 'months': 6})
    mine = world['api'](world['simran']).post('/offers', {'listing': 'sidhu', 'amount_paise': 990000, 'months': 11}).json()
    assert (mine['count'], mine['rank'], mine['max_paise']) == (2, 2, 1020000)
    assert 'Aman' not in str(mine)
    board = world['api'](world['owner_a']).get('/owner/offers').json()
    assert [o['name'] for o in board['offers']] == ['Aman Verma', 'Simran Kaur']


def test_accepting_holds_the_bed_for_24_hours_and_declines_the_rest(world):
    _open(world)
    world['api'](world['aman']).post('/offers', {'listing': 'sidhu', 'amount_paise': 1020000, 'months': 6})
    win = world['api'](world['simran']).post('/offers', {'listing': 'sidhu', 'amount_paise': 1030000, 'months': 11}).json()
    r = world['api'](world['owner_a']).post(f"/owner/offers/{win['id']}/accept")
    assert r.status_code == 200 and r.json()['open'] is False
    b = read(lambda: Booking.objects.get(guest=world['simran']))
    assert b.status == 'hold' and b.rent_paise == 1030000 and b.deposit_paise == 900000   # an offer never raises the deposit
    assert b.hold_expires_at - timezone.now() > timedelta(hours=23)
    assert read(lambda: Offer.objects.get(tenant=world['aman']).status) == 'declined'
    # the tenant's "book" call picks up the held bed instead of a new one
    again = world['api'](world['simran']).post('/bookings', {'listing': 'sidhu'}, idem='k').json()
    assert again['id'] == str(b.id)


def test_unverified_offer_cannot_be_accepted(world):
    _open(world)
    with system():
        o = Offer.objects.create(organisation=world['org_a'], bed=bed(world['a'], '104', 3), tenant=world['unverified'],
                                 amount_paise=1000000, months=11, move_in_on=date(2026, 12, 1))
    r = world['api'](world['owner_a']).post(f'/owner/offers/{o.id}/accept')
    assert r.status_code == 409 and r.json()['code'] == 'tenant_unverified'


def test_owners_see_revealed_ratings_only(world):
    _open(world)
    with system():
        past = stay(bed(world['b'], '204', 1), world['simran'], date(2025, 1, 1), end=date(2025, 12, 1), status='ended')
        rate(past, 4.5, owner_score=4.8, days_ago=1)   # both sides rated: revealed
    world['api'](world['simran']).post('/offers', {'listing': 'sidhu', 'amount_paise': 950000, 'months': 11})
    o = world['api'](world['owner_a']).get('/owner/offers').json()['offers'][0]
    assert (o['score'], o['past_stays']) == (4.8, 1)
