"""Scheduled jobs, health, throttling, request ids, the trust team's notes, and owners' repair contacts."""
import uuid
from datetime import date, timedelta

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.booking.models import Booking
from apps.booking.tasks import release_expired_holds
from apps.core.ledger import balance
from apps.core.rls import system
from apps.maintenance.models import Ticket
from apps.payments import services as pay
from apps.payments.models import Invoice, Payment
from apps.payments.tasks import charge_rent_for_month, settle_all

from .conftest import Api, read
from .factories import stay
from .helpers import bed, period


def test_hold_expiry_job_releases_the_bed(world):
    b = bed(world['a'], '101', 1)
    with system():
        h = Booking.objects.create(organisation=b.organisation, reference='PG-X1', bed=b, guest=world['aman'], status='hold',
                                   stay_period=period(date(2026, 12, 1)), hold_expires_at=timezone.now() - timedelta(seconds=1),
                                   rent_paise=900000, deposit_paise=900000, idempotency_key=uuid.uuid4().hex, request_fingerprint='t')
    assert release_expired_holds.delay().get() == 1
    assert read(lambda: Booking.objects.get(pk=h.pk).status) == 'expired'


def test_monthly_rent_job_is_safe_to_run_twice(world):
    with system():
        stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 9, 1))
    assert charge_rent_for_month.delay().get() == 2
    charge_rent_for_month.delay().get()
    assert read(lambda: Invoice.objects.count()) == 2      # one per resident per month, however often it runs


def test_settlement_moves_collections_to_the_owners_bank(world):
    with system():
        b = stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
        p = pay.create_payment(b, 'invoice', pay.charge_month(b, timezone.localdate()))
        pay.simulate_capture(Payment.objects.get(pk=p.pk))
    assert settle_all.delay().get() == 900000
    with system():
        assert balance(world['org_a'], 'bank') == 900000 and balance(world['org_a'], 'gateway_clearing') == 0
    assert settle_all.delay().get() == 0


def test_health_and_request_ids(db):
    r = Api().get('/health')
    assert r.status_code == 200 and r.json()['database'] is True
    assert len(r.headers['X-Request-Id']) >= 8
    assert Api().c.get('/api/health', HTTP_X_REQUEST_ID='abc123').headers['X-Request-Id'] == 'abc123'


@override_settings(OTP_PER_IP_10MIN=3)
def test_one_network_cannot_spray_codes(db):
    api = Api()
    for n in range(3):
        assert api.post('/auth/otp/start', {'phone': f'98000000{n:02d}'}).status_code == 200
    r = api.post('/auth/otp/start', {'phone': '9800000099'})
    assert r.status_code == 429 and 'network' in r.json()['message']


def test_owner_sees_why_the_pg_was_sent_back(world):
    call_command('make_staff', '+91 99999 00000')
    ch = Api().post('/auth/otp/start', {'phone': '99999 00000'}).json()
    staff = Api(Api().post('/auth/otp/verify', {'challenge_id': ch['challenge_id'], 'code': ch['dev_code']}).json()['token'])
    with system():
        from apps.property.models import Property
        Property.objects.filter(pk=world['a'].pk).update(status='submitted')
    assert staff.post('/staff/properties/sidhu/reject', {'reason': 'The sale deed is unreadable.'}).status_code == 200
    owner = world['api'](world['owner_a'])
    assert owner.get('/owner/today').json()['review_note'] == 'The sale deed is unreadable.'
    assert owner.get('/owner/property').json()['status'] == 'draft'
    assert staff.post('/staff/properties/sidhu/reject', {'reason': 'again'}).status_code == 409   # only while submitted


def test_repair_contacts_are_the_owners_own(world):
    with system():
        b = stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
        t1 = Ticket.objects.create(organisation=world['org_a'], number=1, property=world['a'], room=b.bed.room, raised_by=world['aman'], category='Plumbing', text='Tap leaks')
        t2 = Ticket.objects.create(organisation=world['org_a'], number=2, property=world['a'], room=b.bed.room, raised_by=world['aman'], category='Plumbing', text='Geyser')
    owner = world['api'](world['owner_a'])
    first = owner.get('/owner/tickets').json()
    assert {x['suggested_assignee'] for x in first} == {'Plumber'}                   # a trade, never a made-up person
    owner.post(f'/owner/tickets/{t1.id}/assign', {'assignee': 'Raj Kumar, 98140 12345'})
    again = {x['id']: x for x in owner.get('/owner/tickets').json()}
    assert again[str(t2.id)]['suggested_assignee'] == 'Raj Kumar, 98140 12345'      # remembered for next time
    assert owner.post(f'/owner/tickets/{t2.id}/assign', {}).json()['assignee'] == 'Raj Kumar, 98140 12345'


def test_lapsed_hold_tells_the_tenant(world):
    from apps.core.models import Notification
    b = bed(world['a'], '101', 1)
    with system():
        Booking.objects.create(organisation=b.organisation, reference='PG-X2', bed=b, guest=world['simran'], status='hold',
                               stay_period=period(date(2026, 12, 1)), hold_expires_at=timezone.now() - timedelta(seconds=1),
                               rent_paise=900000, deposit_paise=900000, idempotency_key=uuid.uuid4().hex, request_fingerprint='t')
    release_expired_holds.delay().get()
    assert read(lambda: list(Notification.objects.filter(party=world['simran']).values_list('kind', flat=True))) == ['booking.expired']


def test_housekeeping_keeps_recent_records(db):
    from apps.core.tasks import purge_expired
    from apps.identity.models import OtpChallenge
    Api().post('/auth/otp/start', {'phone': '98000 11111'})
    with system():
        OtpChallenge.objects.create(phone='+919800022222', code_hash='x', expires_at=timezone.now())
        OtpChallenge.objects.filter(phone='+919800022222').update(created_at=timezone.now() - timedelta(days=2))
    assert purge_expired.delay().get() == {'codes': 1, 'replays': 0}
    assert read(lambda: OtpChallenge.objects.count()) == 1


def test_the_website_may_call_the_api(db, settings):
    settings.DEBUG = True   # development: this machine and the local network may call the API
    c = Api().c
    pre = c.options('/api/listings', HTTP_ORIGIN='http://localhost:8081', HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
                    HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization')
    assert pre.status_code == 204 and pre['Access-Control-Allow-Origin'] == 'http://localhost:8081'
    assert 'Authorization' in pre['Access-Control-Allow-Headers']
    assert c.get('/api/listings', HTTP_ORIGIN='https://evil.example').get('Access-Control-Allow-Origin') is None
    settings.CORS_ORIGINS = ['https://pakkaghar.in']
    settings.DEBUG = False
    assert c.get('/api/listings', HTTP_ORIGIN='https://pakkaghar.in')['Access-Control-Allow-Origin'] == 'https://pakkaghar.in'
    assert c.get('/api/listings', HTTP_ORIGIN='http://localhost:8081').get('Access-Control-Allow-Origin') is None
