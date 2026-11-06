"""Owner API: Today (counts and to-dos) and sending the month's bills."""
from django.utils import timezone
from ninja import Router, Schema

from apps.core.api_support import IST, add_months, month_start, party_of, today
from apps.maintenance.models import Ticket
from apps.payments import services as pay
from apps.payments.models import ElectricityRun, Invoice
from apps.property.models import Bed, PayoutAccount

from .. import common
from ..police.services import police_missing
from ..models import Application, Booking, Visit

router = Router(tags=['owner'])


# ---- today ----------------------------------------------------------------------------------------------

class TodoOut(Schema):
    key: str
    text: str
    label: str
    route: str | None = None
    action: str | None = None


class TodayOut(Schema):
    greeting: str
    owner_name: str
    property: str
    property_status: str
    review_note: str | None
    beds_filled: int
    beds_total: int
    rent_unpaid: int
    offers_open: int          # open bids on rooms up for bids
    applications: int         # requests to stay waiting for you
    open_requests: int
    todos: list[TodoOut]


@router.get('/owner/today', response=TodayOut)
def today_view(request):
    p = common.owner_property(request)
    period = month_start(today())
    current = list(common.current_residents(p))
    total = Bed.objects.filter(room__property=p).count()
    unpaid = Invoice.objects.filter(booking__bed__room__property=p, period=period, status='open').count()
    pending = Application.objects.filter(property=p, status='pending')
    offers = pending.filter(amount_paise__isnull=False).count()
    stays = pending.filter(amount_paise__isnull=True).count()
    open_t = Ticket.objects.filter(property=p, status__in=['Raised', 'Assigned']).count()
    todos = []
    for room in p.rooms.filter(offers_open=True):
        n = pending.filter(room=room, amount_paise__isnull=False).count()
        todos.append({'key': f'bids-{room.number}', 'text': f'Room {room.number} is up for bids: {n} bid{"s" if n != 1 else ""} so far', 'label': 'Review', 'route': '/applications'})
    if (stays or offers) and not PayoutAccount.objects.filter(organisation=p.organisation).exists():
        todos.append({'key': 'payout', 'text': 'Add the bank account rent is paid into before you accept anyone', 'label': 'Add', 'route': '/onboarding/owner?step=payouts'})
    if stays:
        todos.append({'key': 'applications', 'text': f'{stays} request{"s" if stays != 1 else ""} to stay', 'label': 'Review', 'route': '/applications'})
    if open_t:
        todos.append({'key': 'tickets', 'text': f'{open_t} maintenance request{"s" if open_t != 1 else ""}', 'label': 'Open', 'route': '/tickets'})
    for b in Booking.objects.filter(bed__room__property=p, status__in=['confirmed', 'active'], agreement__tenant_signed_at__isnull=False,
                                    agreement__owner_signed_at__isnull=True).select_related('guest'):
        todos.append({'key': f'sign-{b.id}', 'text': f'{b.guest.name} signed the agreement. Your signature is next.', 'label': 'Read & sign', 'route': f'/agreement/{b.id}'})
    for b in current + list(Booking.objects.filter(bed__room__property=p, status='confirmed').select_related('guest', 'police')):
        st = b.police.status
        if st == 'submitted':
            todos.append({'key': f'police-{b.id}', 'text': f'{b.guest.name}: police verification submitted, awaiting police', 'label': 'View', 'route': f'/resident/{b.id}'})
        elif st == 'not_started' and not police_missing(b):   # the form is complete: one tap sends it
            todos.append({'key': f'police-{b.id}', 'text': f'{b.guest.name}: police form ready', 'label': 'Submit', 'action': f'police:{b.id}'})
        elif st == 'not_started':
            todos.append({'key': f'police-{b.id}', 'text': f'{b.guest.name}: waiting for their details for the police form', 'label': 'View', 'route': f'/resident/{b.id}'})
    for b in Booking.objects.filter(bed__room__property=p, status='ended', deposit_outcome='Deposit refund in progress').select_related('guest'):
        todos.append({'key': f'deposit-{b.id}', 'text': f'{b.guest.name} moved out: settle the deposit', 'label': 'Settle', 'route': f'/resident/{b.id}'})
    for v in Visit.objects.filter(property=p, status='requested', slot__gte=timezone.now()).select_related('tenant'):
        todos.append({'key': f'visit-{v.id}', 'text': f'{v.tenant.name or "Someone"} asked to visit {v.slot.astimezone(IST):%a %-d %b, %-I %p}'.replace('AM', 'am').replace('PM', 'pm'),
                      'label': 'Confirm', 'action': f'visit:{v.id}'})
    run = ElectricityRun.objects.filter(property=p, period=period).first()
    if not (run and run.sent_at) and pay.electricity_shares(p, add_months(period, -1))['bookings']:
        todos.append({'key': 'bills', 'text': f'{period:%B} electricity bills are ready', 'label': 'Send', 'action': 'send_bills'})
    hour = timezone.now().astimezone(IST).hour
    me = party_of(request)
    return {'greeting': 'Good morning' if hour < 12 else 'Good afternoon' if hour < 17 else 'Good evening', 'owner_name': me.first_name,
            'property': p.name, 'property_status': p.status, 'review_note': (p.attributes or {}).get('review_note'), 'beds_filled': len(current), 'beds_total': total, 'rent_unpaid': unpaid,
            'offers_open': offers, 'applications': stays, 'open_requests': open_t, 'todos': todos}


@router.post('/owner/bills/send', response=TodayOut, summary="Add last month's meter readings to this month's bills")
def send_bills(request):
    p = common.owner_property(request)
    pay.send_electricity(p, today(), request.party)
    return today_view(request)
