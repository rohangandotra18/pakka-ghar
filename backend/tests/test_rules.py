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
