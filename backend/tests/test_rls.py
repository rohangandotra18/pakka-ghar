"""AC-20: one owner, tenant or visitor can never read another's rows, even with direct ORM queries."""
from datetime import date

from django.db import connection

from apps.booking.models import Booking
from .factories import stay
from apps.core.ledger import balance
from apps.core.models import LedgerLine, Notification
from apps.core.rls import set_context, system
from apps.maintenance.models import TrustReport
from apps.payments.models import WebhookEvent
from apps.property.models import Property

from .helpers import bed


def test_owner_cannot_see_another_owners_bookings_or_ledger(world):
    with system():
        stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
        stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1))
    set_context(world['org_b'].id, world['owner_b'].id)
    assert Booking.objects.count() == 1
    assert {b.organisation_id for b in Booking.objects.all()} == {world['org_b'].id}
    assert not LedgerLine.objects.filter(organisation=world['org_a']).exists()
    assert balance(world['org_a'], 'escrow') == 0      # A's deposits are invisible, not zero
    with system():
        assert balance(world['org_a'], 'escrow') == 900000


def test_tenant_sees_only_their_own_stay(world):
    with system():
        stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
        mine = stay(bed(world['a'], '101', 2), world['simran'], date(2026, 8, 1))
    set_context(None, world['simran'].id)
    assert list(Booking.objects.values_list('id', flat=True)) == [mine.id]
    assert set(LedgerLine.objects.values_list('party_id', flat=True)) == {world['simran'].id}


def test_visitors_see_published_listings_only(world):
    with system():
        Property.objects.filter(pk=world['b'].pk).update(status='draft')
    set_context(None, None)
    assert list(Property.objects.values_list('slug', flat=True)) == ['sidhu']
    set_context(world['org_b'].id, world['owner_b'].id)
    assert set(Property.objects.values_list('slug', flat=True)) == {'sidhu', 'gurnoor'}  # own draft + public


def test_cash_report_is_hidden_from_the_owner_it_is_about(world):
    r = world['api'](world['simran']).post('/requests', {'category': 'Asked to pay in cash', 'text': 'Asked for cash at the visit', 'listing': 'sidhu'})
    assert r.status_code == 200, r.content
    set_context(world['org_a'].id, world['owner_a'].id)
    assert TrustReport.objects.count() == 0
    set_context(None, world['simran'].id)
    assert TrustReport.objects.count() == 1
    assert world['api'](world['owner_a']).get('/owner/tickets').json() == []


def test_notifications_and_webhooks_are_private(world):
    with system():
        Notification.objects.create(party=world['aman'], kind='x', title='for Aman')
        WebhookEvent.objects.create(provider='razorpay', event_id='evt_1', payload={})
    set_context(world['org_a'].id, world['owner_a'].id)
    assert Notification.objects.count() == 0 and WebhookEvent.objects.count() == 0
    set_context(None, world['aman'].id)
    assert Notification.objects.count() == 1 and WebhookEvent.objects.count() == 0


def test_raw_sql_is_filtered_too(world):
    with system():
        stay(bed(world['a'], '101', 1), world['aman'], date(2026, 8, 1))
    set_context(None, None)
    with connection.cursor() as c:
        c.execute('SELECT count(*) FROM booking_booking')
        assert c.fetchone()[0] == 0
        c.execute('SELECT count(*) FROM core_ledgerline')
        assert c.fetchone()[0] == 0


def test_api_owner_cannot_open_another_owners_resident(world):
    with system():
        b = stay(bed(world['b'], '204', 1), world['simran'], date(2026, 8, 1))
    r = world['api'](world['owner_a']).get(f'/owner/residents/{b.id}')
    assert r.status_code == 404
    assert world['api'](world['owner_b']).get(f'/owner/residents/{b.id}').status_code == 200
