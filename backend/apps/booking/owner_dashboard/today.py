"""Owner API: Today (counts and to-dos) and sending the month's bills."""
from datetime import timedelta

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
    tone: str = 'normal'          # urgent | soon | normal: how soon it needs the owner


class MonthOut(Schema):
    period: str                   # YYYY-MM
    collected_paise: int
    due_paise: int


class ComingOut(Schema):
    on: str                       # ISO date
    text: str


class HomeBedOut(Schema):
    room: str
    bed: int
    state: str                    # filled | leaving | held | free
    who: str | None = None


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
    # the dashboard
    property_area: str = ''
    collected_paise: int = 0      # rent and electricity received this month
    unpaid_paise: int = 0         # still owed this month
    unpaid_count: int = 0
    free_next_month: int = 0      # beds free on the 1st of next month
    months: list[MonthOut] = []   # the last six months, oldest first
    coming: list[ComingOut] = []  # the next 30 days: move-outs, move-ins, rent day, bills
    beds: list[HomeBedOut] = []


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
    ready = []
    for b in current + list(Booking.objects.filter(bed__room__property=p, status='confirmed').select_related('guest', 'police')):
        st = b.police.status
        if st == 'submitted':
            todos.append({'key': f'police-{b.id}', 'text': f'{b.guest.name}: police verification submitted, awaiting police', 'label': 'View', 'route': f'/resident/{b.id}'})
        elif st == 'not_started' and not police_missing(b):   # the form is complete: one tap sends it
            ready.append(b)
        elif st == 'not_started':
            todos.append({'key': f'police-{b.id}', 'text': f'{b.guest.name}: waiting for their details for the police form', 'label': 'View', 'route': f'/resident/{b.id}'})
    if len(ready) == 1:
        todos.append({'key': f'police-{ready[0].id}', 'text': f'{ready[0].guest.name}: police form ready', 'label': 'Submit', 'action': f'police:{ready[0].id}'})
    elif ready:
        todos.append({'key': 'police-all', 'text': f'{len(ready)} police forms ready', 'label': 'Submit all',
                      'action': 'police:' + ','.join(str(b.id) for b in ready)})
    for b in Booking.objects.filter(bed__room__property=p, status='ended', deposit_outcome='Deposit refund in progress').select_related('guest'):
        by = (b.ended_on + timedelta(days=7)) if b.ended_on else None
        todos.append({'key': f'deposit-{b.id}', 'text': f'{b.guest.name} moved out: settle the deposit{f" by {by:%-d %b}" if by else ""}', 'label': 'Settle', 'route': f'/resident/{b.id}'})
    for v in Visit.objects.filter(property=p, status='requested', slot__gte=timezone.now()).select_related('tenant'):
        todos.append({'key': f'visit-{v.id}', 'text': f'{v.tenant.name or "Someone"} asked to visit {v.slot.astimezone(IST):%a %-d %b, %-I %p}'.replace('AM', 'am').replace('PM', 'pm'),
                      'label': 'Confirm', 'action': f'visit:{v.id}'})
    run = ElectricityRun.objects.filter(property=p, period=period).first()
    if not (run and run.sent_at) and pay.electricity_shares(p, add_months(period, -1))['bookings']:
        todos.append({'key': 'bills', 'text': f'{period:%B} electricity bills are ready', 'label': 'Send', 'action': 'send_bills'})
    for t in todos:   # what loses money or breaks a promise if left goes first
        k = t['key']
        t['tone'] = ('urgent' if k.startswith(('deposit-', 'applications', 'bids-', 'payout')) else
                     'soon' if k.startswith(('police-', 'visit-', 'bills')) else 'normal')
    order = {'urgent': 0, 'soon': 1, 'normal': 2}
    todos.sort(key=lambda t: order[t['tone']])
    hour = timezone.now().astimezone(IST).hour
    me = party_of(request)
    return {'greeting': 'Good morning' if hour < 12 else 'Good afternoon' if hour < 17 else 'Good evening', 'owner_name': me.first_name,
            'property': p.name, 'property_status': p.status, 'review_note': (p.attributes or {}).get('review_note'), 'beds_filled': len(current), 'beds_total': total, 'rent_unpaid': unpaid,
            'offers_open': offers, 'applications': stays, 'open_requests': open_t, 'todos': todos, **_dashboard(p, period, current)}


def _dashboard(p, period, current) -> dict:
    """The numbers on the owner's Home: this month's money, six months of it, the beds and the next 30 days."""
    from datetime import timedelta

    from django.db.models import Sum

    from apps.payments.models import Payment
    from apps.core.rls import system
    t = today()
    for b in current:   # this month's bills, made now if the monthly job hasn't run yet (as Money does)
        with system():
            pay.charge_month(Booking.objects.get(pk=b.pk), period)
    months = []
    for i in range(5, -1, -1):
        m = add_months(period, -i)
        invs = Invoice.objects.filter(booking__bed__room__property=p, period=m).exclude(status='void')
        got = Payment.objects.filter(invoice__in=invs, status='captured').aggregate(s=Sum('amount_paise'))['s'] or 0
        due = sum(inv.total_paise for inv in invs.prefetch_related('lines'))
        months.append({'period': m.strftime('%Y-%m'), 'collected_paise': got, 'due_paise': due})
    this = months[-1]
    unpaid = Invoice.objects.filter(booking__bed__room__property=p, period=period, status='open')
    next_first = add_months(period, 1)
    live = list(Booking.objects.filter(bed__room__property=p, status__in=['hold', 'confirmed', 'active'])
                .select_related('bed__room', 'guest'))
    def ends(b):
        return b.stay_period.upper.astimezone(IST).date() if b.stay_period.upper else None
    def starts(b):
        return b.stay_period.lower.astimezone(IST).date()
    by_bed = {}
    for b in live:
        if starts(b) <= next_first and (ends(b) is None or ends(b) > next_first):
            by_bed[b.bed_id] = b
    free_next = Bed.objects.filter(room__property=p).exclude(pk__in=by_bed.keys()).count()
    beds = []
    current_ids = {b.id for b in current}
    for bed in Bed.objects.filter(room__property=p).select_related('room').order_by('room__number', 'label'):
        b = next((x for x in live if x.bed_id == bed.id and (x.id in current_ids or x.status in ('hold', 'confirmed'))), None)
        if not b:
            beds.append({'room': bed.room.number, 'bed': bed.label, 'state': 'free'})
            continue
        leaving = b.notice_given_on is not None
        state = 'held' if b.status in ('hold', 'confirmed') else 'leaving' if leaving else 'filled'
        beds.append({'room': bed.room.number, 'bed': bed.label, 'state': state, 'who': b.guest.first_name})
    coming = []
    soon = t + timedelta(days=30)
    for b in live:
        if b.notice_given_on and ends(b) and t <= ends(b) <= soon:
            coming.append({'on': ends(b).isoformat(), 'text': f'{b.guest.first_name} leaves Room {b.bed.room.number}'})
        if b.status == 'confirmed' and t <= starts(b) <= soon:
            coming.append({'on': starts(b).isoformat(), 'text': f'{b.guest.first_name} moves into Room {b.bed.room.number}'})
    if current:
        coming.append({'on': next_first.isoformat(), 'text': f'Rent due for {len(current)} resident{"s" if len(current) != 1 else ""}'})
    coming.sort(key=lambda c: c['on'])
    return {'property_area': p.area, 'collected_paise': this['collected_paise'],
            'unpaid_paise': max(0, this['due_paise'] - this['collected_paise']), 'unpaid_count': unpaid.count(),
            'free_next_month': free_next, 'months': months, 'coming': coming[:6], 'beds': beds}


@router.post('/owner/bills/send', response=TodayOut, summary="Add last month's meter readings to this month's bills")
def send_bills(request):
    p = common.owner_property(request)
    pay.send_electricity(p, today(), request.party)
    return today_view(request)
