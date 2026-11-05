"""Owner side: today's to-dos, the bed board, applications and bids, tours, residents, money and the year statement."""
from datetime import date, datetime
from uuid import UUID

from django.db.models import Sum
from django.utils import timezone
from ninja import Router, Schema

from apps.core.api_support import IST, ApiError, add_months, fy_label, month_start, owner_org, party_of, today
from apps.core.ledger import balance
from apps.core.models import LedgerLine
from apps.core.rls import system
from apps.maintenance.models import Ticket
from apps.payments import services as pay
from apps.payments.models import ElectricityRun, Invoice, Reminder
from apps.property.models import Bed, MeterReading, PayoutAccount, Property

from . import services as svc
from .models import Application, Booking, Visit

router = Router(tags=['owner'])


def _prop(request) -> Property:
    org = owner_org(request)
    p = Property.objects.filter(organisation=org).order_by('created_at').first()
    if not p:
        raise ApiError(404, 'no_property', 'Add your property first.')
    svc.activate_started()
    return p


def _current(p: Property):
    now = timezone.now()
    return (Booking.objects.filter(bed__room__property=p, status='active', stay_period__contains=now)
            .select_related('guest', 'bed__room', 'police').order_by('bed__room__number', 'bed__label'))


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
    p = _prop(request)
    period = month_start(today())
    current = list(_current(p))
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
    if stays:
        todos.append({'key': 'applications', 'text': f'{stays} request{"s" if stays != 1 else ""} to stay', 'label': 'Review', 'route': '/applications'})
    if open_t:
        todos.append({'key': 'tickets', 'text': f'{open_t} maintenance request{"s" if open_t != 1 else ""}', 'label': 'Open', 'route': '/tickets'})
    for b in Booking.objects.filter(bed__room__property=p, status__in=['confirmed', 'active'], agreement__tenant_signed_at__isnull=False,
                                    agreement__owner_signed_at__isnull=True).select_related('guest'):
        todos.append({'key': f'sign-{b.id}', 'text': f'{b.guest.name} signed the agreement. Your signature is next.', 'label': 'Read & sign', 'route': f'/agreement/{b.id}'})
    for b in current + list(Booking.objects.filter(bed__room__property=p, status='confirmed').select_related('guest', 'police')):
        st = b.police.status
        if st != 'verified':
            todos.append({'key': f'police-{b.id}', 'text': f'{b.guest.name}: police verification {"submitted, awaiting police" if st == "submitted" else "not started"}',
                          'label': 'View' if st == 'submitted' else 'Fix', 'route': f'/resident/{b.id}'})
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
    p = _prop(request)
    pay.send_electricity(p, today(), request.party)
    return today_view(request)


@router.post('/owner/visits/{visit_id}/confirm', response=TodayOut)
def confirm_visit(request, visit_id: UUID):
    p = _prop(request)
    v = Visit.objects.filter(pk=visit_id, property=p).first()
    if not v:
        raise ApiError(404, 'not_found', 'No such visit.')
    v.status = 'confirmed'
    v.save(update_fields=['status', 'updated_at'])
    from apps.core.api_support import notify
    notify(v.tenant, 'visit.confirmed', f'{p.name} confirmed your visit on {v.slot.astimezone(IST):%A at %-I %p}.'.replace('AM', 'am').replace('PM', 'pm'), org=p.organisation)
    return today_view(request)


@router.post('/owner/visits/{visit_id}/decline', response=TodayOut, summary='Turn down a visit; the tenant is told')
def decline_visit(request, visit_id: UUID):
    p = _prop(request)
    v = Visit.objects.filter(pk=visit_id, property=p, status='requested').first()
    if not v:
        raise ApiError(404, 'not_found', 'No such visit request.')
    v.status = 'cancelled'
    v.save(update_fields=['status', 'updated_at'])
    from apps.core.api_support import notify
    notify(v.tenant, 'visit.declined', f'{p.name} can’t do that visit. Ask for another time in the app.', org=p.organisation)
    return today_view(request)


# ---- bed board --------------------------------------------------------------------------------------------

class BedOut(Schema):
    bed_id: int
    label: int
    who: str | None
    tag: str | None      # leaving | new | offers | free
    note: str


class RoomBoardOut(Schema):
    number: str
    full: bool
    bidding: bool
    bids: int
    beds: list[BedOut]


class BoardOut(Schema):
    free: int
    rooms: list[RoomBoardOut]
    full_rooms: int


@router.get('/owner/beds', response=BoardOut)
def beds(request):
    p = _prop(request)
    now = timezone.now()
    rooms, full, free = [], 0, 0
    for room in p.rooms.prefetch_related('beds'):
        cells, all_full = [], True
        for bed in room.beds.all():
            cur = bed.bookings.filter(status='active', stay_period__contains=now).select_related('guest').first()
            nxt = bed.bookings.filter(status__in=['confirmed', 'hold'], stay_period__startswith__gt=now).select_related('guest').order_by('stay_period').first()
            if cur and cur.notice_given_on:
                all_full = False
                cells.append({'bed_id': bed.id, 'label': bed.label, 'who': cur.guest.first_name, 'tag': 'leaving', 'note': f'leaves {svc.leaves_on(cur):%-d %b}'})
            elif cur:
                cells.append({'bed_id': bed.id, 'label': bed.label, 'who': cur.guest.first_name, 'tag': None, 'note': ''})
            elif nxt:
                all_full = False
                lo = nxt.stay_period.lower.astimezone(IST)
                cells.append({'bed_id': bed.id, 'label': bed.label, 'who': nxt.guest.first_name, 'tag': 'new',
                              'note': f'from {lo:%-d %b}' if nxt.status == 'confirmed' else 'paying deposit'})
            else:
                all_full = False
                free += 1
                cells.append({'bed_id': bed.id, 'label': bed.label, 'who': None, 'tag': 'offers' if room.offers_open else 'free',
                              'note': 'Up for bids' if room.offers_open else 'Free · listed'})
        full += all_full
        rooms.append({'number': room.number, 'full': all_full, 'bidding': room.offers_open, 'beds': cells,
                      'bids': Application.objects.filter(room=room, status='pending', amount_paise__isnull=False).count()})
    return {'free': free, 'rooms': rooms, 'full_rooms': full}


# ---- applications and bids --------------------------------------------------------------------------------

class ApplicantOut(Schema):
    id: UUID
    name: str
    verified: bool
    works_at: str
    score: float | None
    past_stays: int
    status: str
    is_lead: bool


class OwnerApplicationOut(Schema):
    id: UUID
    room: str | None
    room_kind: str
    amount_paise: int | None
    rent_paise: int
    months: int
    move_in_on: date
    message: str
    status: str
    size: int
    members: list[ApplicantOut]
    fits: list[str]          # rooms that have enough free beds together, for an "any room" application
    created_at: datetime


class BiddingRoomOut(Schema):
    number: str
    kind: str
    rent_paise: int
    cap_paise: int
    free: int
    closes_at: datetime | None


class ApplicationsOut(Schema):
    bidding: list[BiddingRoomOut]
    applications: list[OwnerApplicationOut]
    decided: list[OwnerApplicationOut]


def owner_application_out(a: Application) -> dict:
    members = []
    for m in a.members.select_related('party').exclude(status__in=['declined', 'left']):
        rec = svc.tenant_record(m.party) if m.party else {'score': None, 'past_stays': 0}
        members.append({'id': m.id, 'name': m.party.name if m.party else 'Invited', 'verified': bool(m.party and m.party.verified),
                        'works_at': m.party.works_at if m.party else '', 'score': rec['score'], 'past_stays': rec['past_stays'],
                        'status': m.status, 'is_lead': m.is_lead})
    size = len([m for m in members if m['status'] == 'joined'])
    fits = [] if a.room_id or a.status != 'pending' else [r.number for r in svc._rooms_that_fit(a.property, size, a.move_in_on, a.room_kind)]
    return {'id': a.id, 'room': a.room.number if a.room else None, 'room_kind': a.room_kind or (a.room.kind if a.room else ''),
            'amount_paise': a.amount_paise, 'rent_paise': a.amount_paise or (a.room.rent_paise if a.room else 0), 'months': a.months,
            'move_in_on': a.move_in_on, 'message': a.message, 'status': a.status, 'size': size, 'members': members, 'fits': fits,
            'created_at': a.created_at}


@router.get('/owner/applications', response=ApplicationsOut, summary='Requests to stay and bids, best bids first')
def applications(request):
    p = _prop(request)
    from apps.property.services import offer_cap_paise
    bidding = []
    for r in p.rooms.filter(offers_open=True):
        bidding.append({'number': r.number, 'kind': r.get_kind_display(), 'rent_paise': r.rent_paise, 'cap_paise': offer_cap_paise(r.rent_paise),
                        'free': len(svc.free_in_room(r, svc.next_move_in())), 'closes_at': r.offers_close_at})
    live = Application.objects.filter(property=p, status='pending').select_related('room', 'property')
    order = sorted(live, key=lambda a: (a.amount_paise is None, -(a.amount_paise or 0), a.created_at))
    recent = Application.objects.filter(property=p, status__in=['accepted', 'declined']).select_related('room', 'property').order_by('-decided_at')[:10]
    return {'bidding': bidding, 'applications': [owner_application_out(a) for a in order], 'decided': [owner_application_out(a) for a in recent]}


def _app(request, app_id) -> Application:
    p = _prop(request)
    a = Application.objects.filter(pk=app_id, property=p).select_related('room', 'property', 'lead').first()
    if not a:
        raise ApiError(404, 'not_found', 'No such application.')
    return a


class AcceptIn(Schema):
    room: str = ''    # for an "any room" application: which room to put them in


@router.post('/owner/applications/{app_id}/accept', response=ApplicationsOut, summary='Accept: beds are held 24 hours for each person')
def accept(request, app_id: UUID, body: AcceptIn):
    svc.accept(_app(request, app_id), request.party, body.room)
    return applications(request)


class DeclineIn(Schema):
    reason: str = ''


@router.post('/owner/applications/{app_id}/decline', response=ApplicationsOut)
def decline(request, app_id: UUID, body: DeclineIn):
    svc.decline(_app(request, app_id), request.party, body.reason)
    return applications(request)


# ---- residents ----------------------------------------------------------------------------------------------

class ResidentRow(Schema):
    booking_id: UUID
    name: str
    room: str
    since: str
    to: str
    police: str
    rating: float | None
    deposit: str


class ResidentsOut(Schema):
    current: int
    past: int
    items: list[ResidentRow]


@router.get('/owner/residents', response=ResidentsOut)
def residents(request, tab: str = 'current'):
    p = _prop(request)
    cur = Booking.objects.filter(bed__room__property=p, status__in=['active', 'confirmed'])
    past = Booking.objects.filter(bed__room__property=p, status='ended')
    qs = (cur if tab == 'current' else past).select_related('guest', 'bed__room', 'police')
    qs = qs.order_by('bed__room__number', 'bed__label') if tab == 'current' else qs.order_by('-ended_on')
    items = []
    for b in qs:
        frm, to = svc.stay_label(b)
        r = b.ratings.filter(direction='tenant_to_pg').first()
        items.append({'booking_id': b.id, 'name': b.guest.name, 'room': b.bed.room.number, 'since': frm, 'to': to,
                      'police': b.police.get_status_display(), 'rating': float(r.score) if r else None, 'deposit': b.deposit_outcome})
    return {'current': cur.count(), 'past': past.count(), 'items': items}


class ResidentOut(Schema):
    booking_id: UUID
    name: str
    phone: str
    room: str
    status: str
    identity: str
    police: str
    police_missing: list[str]
    agreement: str
    rent_paise: int
    autopay: bool
    deposit_paise: int
    deposit_held_paise: int
    deposit_outcome: str
    since: str
    leaves_on: date | None


def resident_out(b: Booking) -> dict:
    a, pv = b.agreement, b.police
    frm, _ = svc.stay_label(b)
    agreement = ('Signed · e-stamped' if a.stamped_at else 'Signed by both' if a.owner_signed_at else
                 'Waiting for your signature' if a.tenant_signed_at else 'Not signed yet')
    return {'booking_id': b.id, 'name': b.guest.name, 'phone': b.guest.phone, 'room': b.bed.room.number, 'status': b.status,
            'identity': 'Aadhaar verified' if b.guest.verified else 'Not verified', 'police': pv.get_status_display(),
            'police_missing': [m.replace('_', ' ') for m in (pv.packet or {}).get('missing', [])],
            'agreement': agreement, 'rent_paise': b.rent_paise, 'autopay': b.autopay, 'deposit_paise': b.deposit_paise,
            'deposit_held_paise': -balance(b.organisation, 'deposit_liability', b.guest), 'deposit_outcome': b.deposit_outcome,
            'since': frm, 'leaves_on': svc.leaves_on(b)}


def _booking(request, booking_id) -> Booking:
    p = _prop(request)
    b = Booking.objects.filter(pk=booking_id, bed__room__property=p).select_related('guest', 'bed__room__property', 'agreement', 'police').first()
    if not b:
        raise ApiError(404, 'not_found', 'No such resident.')
    return b


@router.get('/owner/residents/{booking_id}', response=ResidentOut)
def resident(request, booking_id: UUID):
    return resident_out(_booking(request, booking_id))


@router.post('/owner/residents/{booking_id}/police/submit', response=ResidentOut, summary='Submit the tenant-verification packet')
def police_submit(request, booking_id: UUID):
    b = _booking(request, booking_id)
    svc.submit_police(b, request.party)
    return resident_out(b)


@router.post('/owner/residents/{booking_id}/police/verified', response=ResidentOut, summary='Record that the police cleared the resident')
def police_verified(request, booking_id: UUID):
    b = _booking(request, booking_id)
    svc.mark_police_verified(b, request.party)
    return resident_out(b)


class SettleIn(Schema):
    deduction_paise: int = 0
    reason: str = ''
    rating: int | None = None


@router.post('/owner/residents/{booking_id}/move-out', response=ResidentOut, summary='Settle the deposit and rate the resident')
def move_out(request, booking_id: UUID, body: SettleIn):
    b = _booking(request, booking_id)
    svc.settle_deposit(b, request.party, body.deduction_paise, body.reason)
    if body.rating:
        svc.owner_rates(b, request.party, body.rating)
    return resident_out(b)


# ---- money --------------------------------------------------------------------------------------------------

class MoneyRow(Schema):
    booking_id: UUID
    invoice_id: UUID
    name: str
    room: str
    units: float
    autopay: bool
    due_paise: int
    paid: bool
    reminded: bool


class RoomUnits(Schema):
    room: str
    units: float
    amount_paise: int


class MoneyOut(Schema):
    period: date
    collected_paise: int
    due_paise: int
    rows: list[MoneyRow]
    rooms: list[RoomUnits]
    read_on: date | None
    tariff_paise: int
    bills_sent: bool
    escrow_paise: int
    next_payout_paise: int
    payout_account: str | None


@router.get('/owner/money', response=MoneyOut)
def money(request):
    p = _prop(request)
    period = month_start(today())
    run = ElectricityRun.objects.filter(property=p, period=period).first()
    sent = bool(run and run.sent_at)
    shares = pay.electricity_shares(p, add_months(period, -1))
    rows, due_total, got = [], 0, 0
    for b in _current(p):
        with system():  # the monthly charge job, run on demand if it hasn't yet
            inv = pay.charge_month(Booking.objects.get(pk=b.pk), period)
        inv = Invoice.objects.prefetch_related('lines').get(pk=inv.pk)
        units = shares['bookings'].get(b.id, 0)
        pending = 0 if sent else int(units * p.tariff_paise)
        due = inv.total_paise + pending
        paid = inv.status == 'paid' and not pending
        due_total += due
        got += pay.invoice_paid_paise(inv)
        rows.append({'booking_id': b.id, 'invoice_id': inv.id, 'name': b.guest.name, 'room': b.bed.room.number, 'units': float(units),
                     'autopay': b.autopay, 'due_paise': due, 'paid': paid,
                     'reminded': Reminder.objects.filter(invoice=inv).exists()})
    meter_read = MeterReading.objects.filter(meter__room__property=p, read_at__lte=timezone.now().replace(day=1)).order_by('-read_at').first()
    acct = PayoutAccount.objects.filter(organisation=p.organisation).order_by('-created_at').first()
    return {'period': period, 'collected_paise': got, 'due_paise': due_total, 'rows': rows,
            'rooms': [{'room': r, 'units': float(u), 'amount_paise': int(u * p.tariff_paise)} for r, u in sorted(shares['rooms'].items())],
            'read_on': meter_read.read_at.astimezone(IST).date() if meter_read else None, 'tariff_paise': p.tariff_paise, 'bills_sent': sent,
            'escrow_paise': balance(p.organisation, 'escrow'), 'next_payout_paise': balance(p.organisation, 'gateway_clearing'),
            'payout_account': f'{acct.bank_name} ••{acct.account_masked[-4:]}' if acct else None}


@router.post('/owner/money/{invoice_id}/remind', response=MoneyOut, summary='Remind in the app and on WhatsApp')
def remind(request, invoice_id: UUID):
    p = _prop(request)
    inv = Invoice.objects.filter(pk=invoice_id, booking__bed__room__property=p).select_related('party').first()
    if not inv:
        raise ApiError(404, 'not_found', 'No such bill.')
    if not Reminder.objects.filter(invoice=inv, created_at__date=today()).exists():
        Reminder.objects.create(organisation=p.organisation, invoice=inv)
        from apps.core.api_support import notify
        notify(inv.party, 'rent.reminder', f'Your {inv.period:%B} bill is due. Pay in the app.', org=p.organisation, invoice=str(inv.id))
    return money(request)


class StatementRow(Schema):
    name: str
    room: str
    rent_paise: int
    electricity_paise: int


class StatementOut(Schema):
    fy: str
    rent_paise: int
    electricity_paise: int
    deductions_paise: int
    standard_deduction_paise: int
    rows: list[StatementRow]
    note: str


@router.get('/owner/statement', response=StatementOut, summary='Year statement for your CA')
def statement(request, fy: str | None = None):
    p = _prop(request)
    fy = fy or fy_label(today())
    start = date(int(fy[:4]), 4, 1)
    end = date(start.year + 1, 4, 1)
    lines = LedgerLine.objects.filter(organisation=p.organisation, journal__created_at__date__gte=start, journal__created_at__date__lt=end)
    tot = lambda code: -(lines.filter(account__code=code).aggregate(s=Sum('amount_paise'))['s'] or 0)  # noqa: E731
    rows = []
    for b in Booking.objects.filter(bed__room__property=p, invoices__period__gte=start, invoices__period__lt=end).distinct().select_related('guest', 'bed__room'):
        inv_lines = [ln for inv in b.invoices.filter(period__gte=start, period__lt=end) for ln in inv.lines.all()]
        rows.append({'name': b.guest.name, 'room': b.bed.room.number,
                     'rent_paise': sum(ln.amount_paise for ln in inv_lines if ln.kind == 'rent'),
                     'electricity_paise': sum(ln.amount_paise for ln in inv_lines if ln.kind == 'electricity')})
    rent = tot('rent_income')
    return {'fy': fy, 'rent_paise': rent, 'electricity_paise': tot('electricity_income'), 'deductions_paise': tot('deductions_income'),
            'standard_deduction_paise': rent * 30 // 100, 'rows': rows,
            'note': 'The 30% standard deduction applies if you declare rent as income from house property. Your CA decides; '
                    'PG income with services such as meals is often business income instead.'}


# ---- owner controls: a room up for bids, room rent, tour hours ------------------------------------------------

class BiddingIn(Schema):
    open: bool


@router.post('/owner/rooms/{number}/bidding', response=BoardOut, summary='Put a room up for bids until Friday 6 pm, or stop')
def toggle_bidding(request, number: str, body: BiddingIn):
    from apps.property.models import Room
    p = _prop(request)
    room = Room.objects.filter(property=p, number=number).first()
    if not room:
        raise ApiError(404, 'not_found', f'No room {number}.')
    if body.open and not room.offers_open:
        svc.open_bidding(room, request.party)
    elif not body.open and room.offers_open:
        svc.close_bidding(room, request.party, reason=f'{p.name} stopped taking bids on Room {number}. You can apply at the listed rent.')
    return beds(request)


class TourHoursIn(Schema):
    days: list[int]       # 0 = Monday
    start: str            # "10:00"
    end: str              # "18:00"
    minutes: int = 30


@router.put('/owner/tour-hours', response=dict, summary='When tenants can book tours')
def tour_hours(request, body: TourHoursIn):
    import re
    p = _prop(request)
    ok = (all(0 <= d <= 6 for d in body.days) and re.fullmatch(r'\d\d:\d\d', body.start) and re.fullmatch(r'\d\d:\d\d', body.end)
          and body.start < body.end and body.minutes in (15, 30, 45, 60))
    if not ok:
        raise ApiError(422, 'bad_hours', 'Pick days, a start before the end (HH:MM), and 15–60 minute tours.')
    p.attributes = {**(p.attributes or {}), 'tour_hours': body.model_dump()}
    p.save(update_fields=['attributes', 'updated_at'])
    return svc.tour_hours(p)


class RentIn(Schema):
    rent_paise: int


@router.patch('/owner/rooms/{number}', response=BoardOut, summary="Change a room's rent per bed (applies to new bookings only)")
def room_rent(request, number: str, body: RentIn):
    from apps.property.models import Room
    p = _prop(request)
    room = Room.objects.filter(property=p, number=number).first()
    if not room:
        raise ApiError(404, 'not_found', f'No room {number}.')
    if not 100000 <= body.rent_paise <= 10000000:
        raise ApiError(422, 'bad_rent', 'Rent per bed must be between ₹1,000 and ₹1,00,000.')
    if room.offers_open and Application.objects.filter(room=room, status__in=['forming', 'pending'], amount_paise__isnull=False).exists():
        raise ApiError(409, 'offers_running', 'Stop the bidding on this room first: the bids were made against the current rent.')
    from apps.core.api_support import audit
    before = {'rent_paise': room.rent_paise}
    room.rent_paise = body.rent_paise
    room.save(update_fields=['rent_paise', 'updated_at'])
    audit(p.organisation, request.party, 'room.rent', room, before, {'rent_paise': body.rent_paise})
    return beds(request)
