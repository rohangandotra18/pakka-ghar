"""Tricity police packets, tariff ceilings, webhooks, metered electricity, and the stay end to end."""
import json
from datetime import date

import pytest

from .factories import meter, stay
from apps.core.rls import system
from apps.jurisdiction.rules import MissingFields, build_packet
from apps.payments import services as pay
from apps.payments.models import Payment, WebhookEvent
from apps.property.models import Room

from .conftest import Api, read
from .helpers import bed


def test_packet_needs_every_field_and_never_the_id_number():
    with pytest.raises(MissingFields) as e:
        build_packet('mohali', {'full_name': 'Simran'}, {})
    assert 'emergency_contact' in e.value.missing and 'previous_address' in e.value.missing
    full = {f: 'x' for f in ('full_name', 'father_or_guardian_name', 'date_of_birth', 'mobile', 'permanent_address', 'id_type',
                             'id_last4', 'photo', 'occupation', 'workplace_or_college', 'move_in_on', 'emergency_contact')}
    p = build_packet('panchkula', full, {'owner_name': 'J', 'owner_mobile': 'm', 'property_address': 'a', 'room_number': '1'})
    assert p['police'] == 'Haryana Police' and 'aadhaar' not in json.dumps(p).lower()


def test_tariff_above_the_ceiling_is_refused(world):
    api = world['api'](world['owner_a'])
    assert api.patch('/owner/property', {'tariff_paise': 1200}).status_code == 422
    assert api.patch('/owner/property', {'tariff_paise': 700}).json()['tariff_paise'] == 700


def test_webhook_signature_and_replays(world):
    with system():
        b = stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
        inv = pay.charge_month(b, date(2026, 11, 1))
        p = pay.create_payment(b, 'invoice', inv)
    raw = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
        'id': 'pay_1', 'order_id': p.provider_order_id, 'amount': p.amount_paise, 'method': 'upi'}}}}).encode()
    c = Api().c
    bad = c.post('/api/webhooks/razorpay', raw, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='nope')
    assert bad.status_code == 401
    for expect in ('ok', 'duplicate'):
        r = c.post('/api/webhooks/razorpay', raw, content_type='application/json',
                   HTTP_X_RAZORPAY_SIGNATURE=pay.sign_webhook(raw), HTTP_X_RAZORPAY_EVENT_ID='evt_9')
        assert r.content.decode() == expect
    assert read(lambda: (Payment.objects.get(pk=p.pk).status, WebhookEvent.objects.count())) == ('captured', 1)


def test_cash_or_wrong_amount_never_captures(world):
    with system():
        b = stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
        p = pay.create_payment(b, 'invoice', pay.charge_month(b, date(2026, 11, 1)))
        assert pay.capture(p, 'pay_x', p.amount_paise, 'cash').status == 'failed'
        p2 = pay.create_payment(b, 'invoice', b.invoices.first())
        assert pay.capture(p2, 'pay_y', p2.amount_paise - 1, 'upi').status == 'failed'
        # the partner kept the money either way, so each can be found and refunded
        from apps.core.models import AuditEvent
        assert Payment.objects.get(pk=p2.pk).provider_payment_id == 'pay_y'
        assert set(AuditEvent.objects.filter(action='payment.rejected').values_list('after__provider_payment_id', flat=True)) == {'pay_x', 'pay_y'}


def test_electricity_split_by_days_lived(world):
    with system():
        room = Room.objects.get(property=world['a'], number='101')
        meter(room, 200, 6)
        from apps.core.api_support import add_months, month_start, today
        last = month_start(add_months(today(), -1))
        stay(bed(world['a'], '101', 1), world['aman'], date(2026, 1, 1))
        stay(bed(world['a'], '101', 2), world['simran'], last.replace(day=16) if last.day == 1 else last)
        shares = pay.electricity_shares(world['a'], last)
    units = sorted(shares['bookings'].values())
    assert sum(units) in (199, 200, 201) and units[0] < units[1]


def test_stay_end_to_end_bill_notice_and_move_out(world):
    with system():
        meter(Room.objects.get(property=world['b'], number='204'), 90, 3)
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1))
    api = world['api'](world['simran'])
    s = api.get('/stay').json()['stay']
    assert s['moved_in'] and s['bill']['total_paise'] == 1000000 and len(s['meter']['daily_kwh']) >= 3
    pid = api.post('/stay/pay', idem='p1').json()['id']
    with system():
        pay.simulate_capture(Payment.objects.get(pk=pid))
    assert api.get('/stay').json()['stay']['bill']['status'] == 'paid'
    assert api.post('/stay/notice').json()['stay']['leaves_on']
    h = api.post('/stay/end', {'aspects': {'Cleanliness': 5, 'Food': 4, 'Owner response': 5, 'Value': 4}, 'deposit_on_time': True}).json()
    assert h['items'][0]['rated'] == 4.5 and h['items'][0]['deposit'] == 'Deposit refund in progress'
    owner = world['api'](world['owner_b'])
    bid = h['items'][0]['booking_id']
    r = owner.post(f'/owner/residents/{bid}/move-out', {'deduction_paise': 200000, 'reason': 'a broken chair', 'rating': 5}).json()
    assert r['deposit_outcome'] == '₹2,000 kept for a broken chair' and r['deposit_held_paise'] == 0


def test_notice_never_runs_past_the_agreement(world):
    """With ten days left on the agreement, notice ends the stay on the agreement's last day, not a month later
    (which would also run into the next resident's booking of the bed)."""
    from datetime import timedelta

    from apps.core.api_support import today
    with system():
        end = today() + timedelta(days=10)
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 1, 1), end=end)
    s = world['api'](world['simran']).post('/stay/notice').json()['stay']
    assert s['leaves_on'] == end.isoformat()


def test_reminders_only_for_unpaid_bills_and_the_year_statement(world):
    with system():
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1))
    tenant, owner = world['api'](world['simran']), world['api'](world['owner_b'])
    tenant.get('/stay')                                       # this month's bill exists once the stay is read
    row = owner.get('/owner/money').json()['rows'][0]
    assert owner.post(f"/owner/money/{row['invoice_id']}/remind").status_code == 200
    pid = tenant.post('/stay/pay', idem='p9').json()['id']
    with system():
        pay.simulate_capture(Payment.objects.get(pk=pid))
    assert owner.post(f"/owner/money/{row['invoice_id']}/remind").json()['code'] == 'already_paid'
    assert owner.get('/owner/statement?fy=2026-27').status_code == 200
    for bad in ('abc', '2026', '2026-29'):
        assert owner.get(f'/owner/statement?fy={bad}').json()['code'] == 'bad_year'


def test_owner_can_rate_after_settling_the_deposit_separately(world):
    with system():
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1))
    api = world['api'](world['simran'])
    h = api.post('/stay/end', {'aspects': {'Cleanliness': 4, 'Food': 4, 'Owner response': 4, 'Value': 4}}).json()
    bid = h['items'][0]['booking_id']
    owner = world['api'](world['owner_b'])
    # the deposit factory row has no ledger entry, so post one the way a captured deposit would
    from apps.booking.models import Booking
    from apps.core.ledger import post
    with system():
        b = Booking.objects.get(pk=bid)
        post(b.organisation, 'deposit_captured', 'Deposit', [('escrow', None, b.deposit_paise), ('deposit_liability', b.guest, -b.deposit_paise)])
    assert owner.post(f'/owner/residents/{bid}/move-out', {}).status_code == 200                   # settle only
    r = owner.post(f'/owner/residents/{bid}/move-out', {'rating': 4})                            # rate later
    assert r.status_code == 200, r.content
    assert owner.post(f'/owner/residents/{bid}/move-out', {}).json()['code'] == 'nothing_held'   # can't settle twice
    assert owner.post(f'/owner/residents/{bid}/police/submit').json()['code'] == 'not_booked'
    assert [x['score'] for x in api.get('/me/data').json()['ratings_received']] == [4.0]   # owners' ratings of you are yours to see
