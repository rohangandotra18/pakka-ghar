"""From an empty database: a new owner lists a PG, the trust team approves it, a tenant finds and books it."""
import uuid

from django.core.management import call_command

from apps.core.rls import system
from apps.maintenance.models import TrustReport
from apps.property.models import Property

from .conftest import Api, read
from .helpers import accept


def sign_in(phone):
    ch = Api().post('/auth/otp/start', {'phone': phone}).json()
    return Api(Api().post('/auth/otp/verify', {'challenge_id': ch['challenge_id'], 'code': ch['dev_code']}).json()['token'])


def verify(api):
    txn = api.post('/kyc/digilocker/start').json()['txn']
    return api.post('/kyc/digilocker/complete', {'txn': txn, 'auth_code': 'ok'}).json()


def test_new_owner_to_first_booking(db):
    call_command('make_staff', '+91 99999 00000', name='Trust Team')
    staff = sign_in('99999 00000')
    owner = sign_in('98111 22222')
    verify(owner)
    owner.patch('/me', {'name': 'Harpreet Gill'})
    assert owner.get('/owner/property').status_code == 403          # not an owner until they list
    p = owner.post('/owner/property', {'name': 'Gill Girls PG', 'address': 'House 12, Sector 8-B', 'area': 'Sector 8', 'gender': 'Girls'})
    assert p.status_code == 200 and p.json()['status'] == 'draft'
    assert Api().get('/listings/gill-girls-pg').status_code == 404    # drafts are invisible
    assert owner.post('/owner/property/submit').status_code == 422    # nothing filled in yet
    owner.post('/owner/rooms', {'kind': 'double', 'rooms': 2, 'rent_paise': 850000})
    owner.put('/owner/property/pin', {'lat': 30.7415, 'lng': 76.7900})
    owner.post('/owner/documents/sale_deed?file_name=deed.pdf')
    owner.post('/owner/no-cash-pledge')
    assert owner.post('/owner/property/submit').json()['status'] == 'submitted'
    assert owner.get('/staff/queue').status_code == 403                # owners aren't staff
    q = staff.get('/staff/queue').json()
    assert [x['id'] for x in q['properties']] == ['gill-girls-pg'] and q['properties'][0]['beds'] == 4
    assert staff.post('/staff/properties/gill-girls-pg/approve').status_code == 200
    found = Api().get('/listings?lat=30.7412&lng=76.7788').json()
    assert [x['id'] for x in found] == ['gill-girls-pg'] and found[0]['verified_owner'] and found[0]['free'] == 4
    tenant = sign_in('98222 33333')
    verify(tenant)
    app = tenant.post('/applications', {'listing': 'gill-girls-pg', 'message': 'Final-year student at PU'}).json()
    assert app['status'] == 'pending'
    queue = owner.get('/owner/applications').json()['applications']
    assert [a['id'] for a in queue] == [app['id']] and queue[0]['fits'] == ['101', '102']
    assert accept(owner, app['id'], '102').json()['code'] == 'payout_first'     # the bank is asked for at the first accept
    owner.post('/owner/payout', {'bank_name': 'SBI', 'account_number': '30012345678', 'ifsc': 'SBIN0001234'})
    assert accept(owner, app['id'], '102').status_code == 200
    b = tenant.post('/bookings', {'listing': 'gill-girls-pg'}, idem=uuid.uuid4().hex).json()
    assert (b['room'], b['rent_paise'], b['status']) == ('102', 850000, 'hold')
    assert b['agreement']['owner_signed'] and not b['agreement']['tenant_signed']
    assert set(b['police_missing']) >= {'father_or_guardian_name', 'date_of_birth'}   # asked before move-in, not at sign-up


def test_confirmed_cash_report_pauses_the_listing(world):
    call_command('make_staff', '+91 99999 00000')
    staff = sign_in('99999 00000')
    world['api'](world['simran']).post('/requests', {'category': 'Asked to pay in cash', 'text': 'Owner wants cash', 'listing': 'sidhu'})
    rid = staff.get('/staff/queue').json()['reports'][0]['id']
    assert staff.post(f'/staff/reports/{rid}/resolve', {'outcome': 'confirmed'}).json()['status'] == 'confirmed'
    assert read(lambda: Property.objects.get(slug='sidhu').status) == 'paused'
    assert Api().get('/listings').json() and 'sidhu' not in [x['id'] for x in Api().get('/listings').json()]
    assert read(lambda: TrustReport.objects.get().status) == 'confirmed'


def test_owner_puts_a_room_up_for_bids_and_stops(world):
    owner = world['api'](world['owner_a'])
    assert owner.post('/owner/rooms/104/bidding', {'open': True}).status_code == 200
    bid = world['api'](world['simran']).post('/applications', {'listing': 'sidhu', 'room': '104', 'amount_paise': 950000}).json()
    assert owner.patch('/owner/rooms/104', {'rent_paise': 950000}).status_code == 409   # bids made against the old rent
    owner.post('/owner/rooms/104/bidding', {'open': False})
    mine = world['api'](world['simran']).get('/applications/mine').json()
    assert mine[0]['id'] == bid['id'] and mine[0]['status'] == 'declined'
    assert owner.patch('/owner/rooms/104', {'rent_paise': 950000}).status_code == 200


def test_reset_data_needs_debug_and_yes(db):
    with system():
        assert Property.objects.count() == 0
    call_command('reset_data')  # refuses without --yes; must not raise


def test_changing_what_was_verified_sends_a_live_pg_back_for_checking(world):
    """After approval, the details the trust team checked (name, address, place, the pin) can't silently change:
    editing them sends the PG back for a check. Meals and the tariff stay editable."""
    from apps.property.models import Property
    owner = world['api'](world['owner_a'])
    assert owner.patch('/owner/property', {'meals': '2 meals'}).json()['status'] == 'published'
    p = read(lambda: Property.objects.get(slug='sidhu'))
    assert owner.put('/owner/property/pin', {'lat': float(p.lat) + 0.0004, 'lng': float(p.lng)}).json()['status'] == 'published'  # ~45 m
    assert owner.patch('/owner/property', {'address': 'Somewhere else 9'}).json()['status'] == 'submitted'
    assert read(lambda: Property.objects.get(slug='sidhu').status) == 'submitted'
    assert read(lambda: Property.objects.get(slug='sidhu').attributes['recheck']) == 'changed address'


def test_moving_the_pin_far_sends_a_live_pg_back_for_checking(world):
    from apps.property.models import Property
    owner = world['api'](world['owner_a'])
    p = read(lambda: Property.objects.get(slug='sidhu'))
    assert owner.put('/owner/property/pin', {'lat': float(p.lat) + 0.01, 'lng': float(p.lng)}).json()['status'] == 'submitted'  # ~1 km


def test_a_too_long_value_is_a_clear_422_not_a_server_error(world):
    r = world['api'](world['owner_a']).patch('/owner/property', {'address': 'x' * 500})
    assert r.status_code == 422 and r.json()['code'] == 'too_long'
    assert read(lambda: Property.objects.get(slug='sidhu').address) != 'x' * 500


def test_search_refuses_a_place_that_isnt_one(world):
    for qs in ('lat=nan&lng=76.7', 'lat=95&lng=76.7', 'lat=30.7', 'lng=76.7&lat=30.7&radius_km=nan'):
        r = Api().get(f'/listings?{qs}')
        assert r.status_code == 422, qs
    assert Api().get('/listings?q=' + 'sector ' * 50).status_code == 200


def test_a_confirmed_cash_report_also_pauses_a_pg_under_recheck(world):
    call_command('make_staff', '+91 99999 00000')
    staff = sign_in('99999 00000')
    world['api'](world['owner_a']).patch('/owner/property', {'address': 'Somewhere else 9'})   # back for a check
    world['api'](world['simran']).post('/requests', {'category': 'Asked to pay in cash', 'text': 'Owner wants cash', 'listing': 'sidhu'})
    rid = staff.get('/staff/queue').json()['reports'][0]['id']
    staff.post(f'/staff/reports/{rid}/resolve', {'outcome': 'confirmed'})
    assert read(lambda: Property.objects.get(slug='sidhu').status) == 'paused'
    assert staff.post('/staff/properties/sidhu/approve').status_code == 409
