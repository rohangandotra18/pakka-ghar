"""The three rules decided on 2026-11-06: instant booking (owner's choice), rent for unserved notice, and the
deposit returned automatically on day 7 after move-out."""
from datetime import date, timedelta

from apps.booking.models import Booking
from apps.booking.stay.services import settle_overdue_deposits
from apps.core.api_support import today
from apps.core.ledger import balance, post
from apps.core.models import Notification
from apps.core.rls import system

from .conftest import read
from .factories import stay
from .helpers import bed


def _instant_on(owner, room):
    st = owner.post(f'/owner/rooms/{room}/instant/start').json()
    return owner.post(f'/owner/rooms/{room}/instant', {'on': True, 'challenge_id': st['challenge_id'], 'code': st['dev_code']})


def test_instant_booking_holds_the_bed_signed_without_waiting(world):
    owner, tenant = world['api'](world['owner_a']), world['api'](world['simran'])
    assert owner.post('/owner/rooms/101/instant', {'on': True, 'challenge_id': '00000000-0000-0000-0000-000000000000', 'code': '1'}).status_code == 400
    r = _instant_on(owner, '101')
    assert r.status_code == 200 and next(x for x in r.json()['rooms'] if x['number'] == '101')['instant']
    assert next(x for x in tenant.get('/listings/sidhu').json()['rooms'] if x['number'] == '101')['instant']
    a = tenant.post('/applications', {'listing': 'sidhu', 'room': '101'}).json()
    assert a['status'] == 'accepted' and a['my_booking_id']
    b = tenant.get(f"/bookings/{a['my_booking_id']}").json()
    assert b['status'] == 'hold' and b['agreement']['owner_signed'] and not b['agreement']['tenant_signed']
    assert read(lambda: Notification.objects.filter(party=world['owner_a'], kind='application.instant').count()) == 1


def test_instant_booking_is_off_by_default_and_never_on_a_room_up_for_bids(world):
    owner, tenant = world['api'](world['owner_a']), world['api'](world['simran'])
    assert tenant.post('/applications', {'listing': 'sidhu', 'room': '101'}).json()['status'] == 'pending'
    _instant_on(owner, '104')
    owner.post('/owner/rooms/104/bidding', {'open': True})
    board = owner.get('/owner/beds').json()
    assert next(x for x in board['rooms'] if x['number'] == '104')['instant'] is False      # bids switched it off
    assert owner.post('/owner/rooms/104/instant/start').json()['code'] == 'bidding_on'


def test_leaving_before_the_notice_ends_charges_the_unserved_days(world):
    with system():
        b = stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1), rent=900000)
    api = world['api'](world['simran'])
    st = api.get('/stay').json()['stay']
    assert st['leave_now_charge_paise'] == 900000            # no notice given: a full month (no rent paid this month)
    assert st['notice_ends_on'] == (today() + timedelta(days=30)).isoformat()
    api.post('/stay/notice')
    assert api.get('/stay').json()['stay']['leave_now_charge_paise'] == 900000   # the notice has just started
    api.post('/stay/end', {'aspects': {'Cleanliness': 4, 'Food': 4, 'Owner response': 4, 'Value': 4}})
    assert read(lambda: Booking.objects.get(pk=b.pk).attributes['notice_charge_paise']) == 900000
    note = read(lambda: Notification.objects.filter(party=world['owner_b'], kind='booking.ended').first().title)
    assert 'unserved notice' in note and 'returned automatically' in note


def test_after_serving_the_notice_nothing_is_charged(world):
    with system():
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1), rent=900000, notice_on=today() - timedelta(days=30),
             end=today())
    assert world['api'](world['simran']).get('/stay').json()['stay']['leave_now_charge_paise'] == 0


def _ended(world, days_ago, charge=0):
    with system():
        b = stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1), status='ended', end=today() - timedelta(days=days_ago),
                 deposit_outcome='Deposit refund in progress')
        b.attributes = {'notice_charge_paise': charge}
        b.save(update_fields=['attributes'])
        post(b.organisation, 'deposit_captured', 'Deposit', [('escrow', None, b.deposit_paise), ('deposit_liability', b.guest, -b.deposit_paise)])
    return b


def test_owners_are_reminded_on_day_3_then_the_deposit_returns_on_day_7(world):
    b = _ended(world, 3)
    settle_overdue_deposits()
    settle_overdue_deposits()                                   # runs hourly: one reminder, not one an hour
    assert read(lambda: Notification.objects.filter(party=world['owner_b'], kind='deposit.reminder').count()) == 1
    assert read(lambda: Booking.objects.get(pk=b.pk).deposit_outcome) == 'Deposit refund in progress'
    with system():
        Booking.objects.filter(pk=b.pk).update(ended_on=today() - timedelta(days=7))
    assert settle_overdue_deposits() == 1
    assert read(lambda: balance(world['org_b'], 'deposit_liability', world['simran'])) == 0
    assert read(lambda: Notification.objects.filter(party=world['simran'], kind='deposit.settled').count()) == 1
    assert settle_overdue_deposits() == 0                       # settled once only


def test_the_automatic_refund_keeps_only_the_unserved_notice(world):
    b = _ended(world, 8, charge=300000)
    settle_overdue_deposits()
    assert read(lambda: Booking.objects.get(pk=b.pk).deposit_outcome).startswith('₹3,000 kept for rent for unserved notice')
    assert read(lambda: balance(world['org_b'], 'deductions_income')) == -300000


def test_the_owner_home_has_money_beds_and_whats_coming(world):
    with system():
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1), rent=900000, notice_on=today(), end=today() + timedelta(days=20))
    t = world['api'](world['owner_b']).get('/owner/today').json()
    assert len(t['months']) == 6 and t['months'][-1]['period'] == today().strftime('%Y-%m')
    assert t['unpaid_paise'] >= 900000 and t['unpaid_count'] == 1
    assert {'filled', 'leaving', 'free'} >= {b['state'] for b in t['beds']} and any(b['state'] == 'leaving' for b in t['beds'])
    assert any('leaves Room 204' in c['text'] for c in t['coming'])
    assert t['free_next_month'] >= 1
    assert all(x['tone'] in ('urgent', 'soon', 'normal') for x in t['todos'])
