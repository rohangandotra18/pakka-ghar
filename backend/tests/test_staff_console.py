"""What the trust team's console depends on: /api/me says who is staff, and the trust team's own organisation is not
listed as a PG the person runs."""
from django.core.management import call_command

from apps.core.models import Party

from .conftest import Api, token_for


def _staff_api():
    call_command('make_staff', '+91 99999 00000')
    return Api(token_for(Party.objects.get(phone='+919999900000')))


def test_staff_member_is_flagged_and_is_not_listed_as_an_owner(world):
    me = _staff_api().get('/me').json()
    assert me['staff'] is True
    assert me['memberships'] == []          # the app treats "has memberships" as "runs a PG"


def test_tenants_and_owners_are_not_staff(world):
    tenant = world['api'](world['simran']).get('/me').json()
    assert tenant['staff'] is False and tenant['memberships'] == []
    owner = world['api'](world['owner_a']).get('/me').json()
    assert owner['staff'] is False
    assert [m['organisation_id'] for m in owner['memberships']] == [str(world['org_a'].id)]


def test_a_person_who_is_both_owner_and_staff_keeps_only_the_pg(world):
    call_command('make_staff', world['owner_a'].phone)
    me = world['api'](world['owner_a']).get('/me').json()
    assert me['staff'] is True
    assert [m['name'] for m in me['memberships']] == ['Sidhu Boys PG']


def test_the_queue_is_for_staff_only(world):
    r = world['api'](world['simran']).get('/staff/queue')
    assert r.status_code == 403 and r.json()['code'] == 'not_staff'
    assert world['api'](world['owner_a']).get('/staff/queue').status_code == 403
    assert _staff_api().get('/staff/queue').status_code == 200
