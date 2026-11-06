"""AC-12 and AC-18: bookings can never overlap on a bed; holds expire; cancelling reverses the deposit."""
import uuid
from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.booking.models import Booking
from apps.booking.bookings.services import expire_holds
from apps.core.ledger import balance
from apps.core.rls import system

from .conftest import read
from .helpers import accepted, sign, bed, period


def _booking(b, guest, start, status='confirmed', months=11, **kw):
    return Booking.objects.create(organisation=b.organisation, reference='PG-' + uuid.uuid4().hex[:8], bed=b, guest=guest,
                                  status=status, stay_period=period(start, months), rent_paise=900000, deposit_paise=900000,
                                  idempotency_key=uuid.uuid4().hex, request_fingerprint='t', **kw)


def test_database_refuses_overlapping_bookings_on_one_bed(world):
    b = bed(world['a'], '101', 1)
    with system():
        _booking(b, world['aman'], date(2026, 12, 1))
        with pytest.raises(IntegrityError, match='exclude_space_double_booking'), transaction.atomic():
            _booking(b, world['simran'], date(2027, 3, 1))
        _booking(bed(world['a'], '101', 2), world['simran'], date(2027, 3, 1))           # another bed is fine
        _booking(b, world['simran'], date(2027, 11, 1))                                  # after the first ends is fine
        _booking(b, world['unverified'], date(2027, 3, 1), status='cancelled')         # cancelled never blocks


def test_expired_hold_stops_blocking(world):
    b = bed(world['a'], '101', 1)
    with system():
        h = _booking(b, world['aman'], date(2026, 12, 1), status='hold', hold_expires_at=timezone.now() - timedelta(minutes=1))
    assert expire_holds() == 1
    with system():
        _booking(b, world['simran'], date(2026, 12, 1))
        h.refresh_from_db()
    assert h.status == 'expired'


def _book(api, listing='sidhu', key=None):
    return api.post('/bookings', {'listing': listing}, idem=key or uuid.uuid4().hex)


def test_booking_flow_deposit_into_escrow(world):
    api = accepted(world, world['simran'], world['owner_a'])
    r = _book(api)
    assert r.status_code == 200, r.content
    bk = r.json()
    assert bk['status'] == 'hold' and bk['deposit_paise'] == 900000
    sign(api, bk['id'])
    pay = api.post(f"/bookings/{bk['id']}/deposit", idem='d1').json()
    from apps.payments.services import simulate_capture
    from apps.payments.models import Payment
    with system():
        simulate_capture(Payment.objects.get(pk=pay['id']))
    assert api.get(f"/bookings/{bk['id']}").json()['status'] == 'confirmed'
    assert read(lambda: balance(world['org_a'], 'escrow')) == 900000
    assert read(lambda: balance(world['org_a'], 'deposit_liability', world['simran'])) == -900000


def test_idempotency_replays_and_refuses_reuse(world):
    api = accepted(world, world['simran'], world['owner_a'])
    first = _book(api, key='same-key')
    again = _book(api, key='same-key')
    assert again.json()['id'] == first.json()['id'] and again.headers.get('Idempotent-Replay') == 'true'
    clash = api.post('/bookings', {'listing': 'gurnoor'}, idem='same-key')
    assert clash.status_code == 409 and clash.json()['code'] == 'idempotency_key_reused'
    assert api.post('/bookings', {'listing': 'sidhu'}).status_code == 400  # no key at all


def test_unverified_cannot_book(world):
    r = world['api'](world['unverified']).post('/applications', {'listing': 'sidhu'})
    assert r.status_code == 403 and r.json()['code'] == 'verify_identity'
    assert read(lambda: Booking.objects.count()) == 0  # the failed request wrote nothing


def test_booking_needs_an_accepted_application(world):
    r = _book(world['api'](world['simran']))
    assert r.status_code == 409 and r.json()['code'] == 'apply_first'


def test_cancel_reverses_the_deposit_with_a_contra_entry(world):
    api = accepted(world, world['simran'], world['owner_a'])
    bk = _book(api).json()
    sign(api, bk['id'])
    pay = api.post(f"/bookings/{bk['id']}/deposit", idem='d2').json()
    from apps.payments.models import Payment
    from apps.payments.services import simulate_capture
    with system():
        simulate_capture(Payment.objects.get(pk=pay['id']))
    assert api.post(f"/bookings/{bk['id']}/cancel").json()['status'] == 'cancelled'
    from apps.core.models import Journal
    kinds = read(lambda: sorted(Journal.objects.values_list('kind', flat=True)))
    assert kinds == ['deposit_captured', 'deposit_captured_reversal']
    assert read(lambda: balance(world['org_a'], 'escrow')) == 0


def test_a_deposit_that_lands_after_cancelling_is_refunded(world):
    """The tenant cancels while their UPI payment is still in flight; when the capture arrives, the money goes
    straight back instead of sitting in escrow against a cancelled booking."""
    from apps.payments.models import Payment
    from apps.payments.services import simulate_capture
    api = accepted(world, world['simran'], world['owner_a'])
    bk = _book(api).json()
    sign(api, bk['id'])
    pay = api.post(f"/bookings/{bk['id']}/deposit", idem='d3').json()
    assert api.post(f"/bookings/{bk['id']}/cancel").json()['status'] == 'cancelled'
    with system():
        simulate_capture(Payment.objects.get(pk=pay['id']))
    assert read(lambda: Payment.objects.get(pk=pay['id']).status) == 'refunded'
    assert read(lambda: balance(world['org_a'], 'escrow')) == 0
    assert read(lambda: Booking.objects.get(pk=bk['id']).status) == 'cancelled'


def test_the_owner_hears_when_a_tenant_cancels(world):
    from apps.core.models import Notification
    api = accepted(world, world['simran'], world['owner_a'])
    bk = _book(api).json()
    api.post(f"/bookings/{bk['id']}/cancel")
    titles = read(lambda: list(Notification.objects.filter(party=world['owner_a'], kind='booking.cancelled').values_list('title', flat=True)))
    assert len(titles) == 1 and 'cancelled' in titles[0] and 'free again' in titles[0]


def test_ending_a_stay_before_moving_in_is_refused(world):
    """Before move-in the way out is cancelling, which refunds the deposit in full. Ending and rating would leave the
    deposit for the owner to settle, with deductions, for a stay that never happened."""
    from apps.payments.models import Payment
    from apps.payments.services import simulate_capture
    api = accepted(world, world['simran'], world['owner_a'])
    bk = _book(api).json()
    sign(api, bk['id'])
    pay = api.post(f"/bookings/{bk['id']}/deposit", idem='d9').json()
    with system():
        simulate_capture(Payment.objects.get(pk=pay['id']))
    r = api.post('/stay/end', {'aspects': {'Cleanliness': 1, 'Food': 1, 'Owner response': 1, 'Value': 1}})
    assert r.status_code == 409 and r.json()['code'] == 'not_moved_in'
    assert read(lambda: Booking.objects.get(pk=bk['id']).status) == 'confirmed'
