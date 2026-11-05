"""Data export and erasure, visits, and a listing search whose cost doesn't grow with the number of PGs."""
from datetime import date

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.models import Party
from apps.core.rls import system
from apps.property.models import Bed

from .conftest import Api, read
from .factories import make_property, org_with_owner, person, stay
from .helpers import bed


def test_export_has_only_my_rows(world):
    with system():
        stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1))
    d = world['api'](world['simran']).get('/me/data').json()
    assert d['profile']['phone'] == '+919876543210' and d['profile']['aadhaar_last4']
    assert [b['pg'] for b in d['bookings']] == ['Gurnoor Girls PG']   # not Aman's
    assert 'aadhaar_masked' not in str(d)


def test_erasure_is_refused_while_anything_is_owed(world):
    with system():
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1))
    api = world['api'](world['simran'])
    assert api.post('/me/delete', {'confirm': 'yes'}).status_code == 422
    r = api.post('/me/delete', {'confirm': 'DELETE'})
    assert r.status_code == 409 and r.json()['code'] == 'stay_open'
    assert world['api'](world['owner_a']).post('/me/delete', {'confirm': 'DELETE'}).json()['code'] == 'owns_pg'


def test_erasure_removes_identity_and_keeps_records(world):
    with system():
        past = stay(bed(world['b'], '204', 1), world['simran'], date(2025, 1, 1), end=date(2025, 12, 1), status='ended')
    api = world['api'](world['simran'])
    r = api.post('/me/delete', {'confirm': 'DELETE'})
    assert r.status_code == 200 and 'ledger' in r.json()['kept']
    p = read(lambda: Party.objects.get(pk=world['simran'].pk))
    assert p.name == 'Deleted user' and p.phone.startswith('del-') and not p.aadhaar_masked and p.profile == {}
    assert api.get('/me').status_code == 401                                   # signed out everywhere
    assert read(lambda: past.__class__.objects.filter(pk=past.pk).exists())   # the booking record stays
    # the same phone number can sign up again as a new person
    ch = Api().post('/auth/otp/start', {'phone': '98765 43210'}).json()
    assert Api().post('/auth/otp/verify', {'challenge_id': ch['challenge_id'], 'code': ch['dev_code']}).json()['new_account'] is True


def test_visits_listed_cancelled_and_not_doubled(world):
    api = world['api'](world['simran'])
    a = api.post('/visits', {'listing': 'gurnoor'}).json()
    assert api.post('/visits', {'listing': 'gurnoor'}).json()['id'] == a['id']   # asking twice books one visit
    assert [v['status'] for v in api.get('/visits/mine').json()] == ['requested']
    assert api.post(f"/visits/{a['id']}/cancel").json()['status'] == 'cancelled'
    b = api.post('/visits', {'listing': 'gurnoor'}).json()
    owner = world['api'](world['owner_b'])
    assert any(t['key'] == f"visit-{b['id']}" for t in owner.get('/owner/today').json()['todos'])
    owner.post(f"/owner/visits/{b['id']}/decline")
    assert {v['status'] for v in api.get('/visits/mine').json()} == {'cancelled'}


def _add_pgs(n, start):
    with system():
        for i in range(start, start + n):
            o = org_with_owner(f'PG {i}', person(f'Owner {i}'))
            p = make_property(o, f'pg-{i}', f'PG {i}', 'Boys', 'Sector 15', 'x', 'chandigarh', 30.75 + i * 0.001, 76.77, '3 meals',
                              [('101', 'double', 9000), ('102', 'triple', 8000)])
            for b in list(Bed.objects.filter(room__property=p))[:3]:
                stay(b, person(f'R{i}-{b.id}'), date(2026, 3, 1))


def test_search_cost_does_not_grow_with_pgs(db):
    _add_pgs(2, 0)
    with CaptureQueriesContext(connection) as few:
        assert len(Api().get('/listings?lat=30.7543&lng=76.7713').json()) == 2
    _add_pgs(10, 2)
    with CaptureQueriesContext(connection) as many:
        assert len(Api().get('/listings?lat=30.7543&lng=76.7713').json()) == 12
    assert len(many.captured_queries) == len(few.captured_queries) <= 20
