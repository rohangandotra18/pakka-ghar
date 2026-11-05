"""From an empty database: a new owner lists a PG, the trust team approves it, a tenant finds and books it."""
import uuid

from django.core.management import call_command

from apps.core.rls import system
from apps.maintenance.models import TrustReport
from apps.property.models import Property

from .conftest import Api, read


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
    owner.post('/owner/payout', {'bank_name': 'SBI', 'account_number': '30012345678', 'ifsc': 'SBIN0001234'})
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
    owner.post(f"/owner/applications/{app['id']}/accept", {'room': '102'})
    b = tenant.post('/bookings', {'listing': 'gill-girls-pg'}, idem=uuid.uuid4().hex).json()
    assert (b['room'], b['rent_paise'], b['status']) == ('102', 850000, 'hold')


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
