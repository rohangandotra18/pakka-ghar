"""Owner side: today's to-dos, the bed board, offers, residents, money and the year statement."""
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
from apps.property.services import offer_cap_paise

from . import services as svc
from .models import Booking, Offer, Visit

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
    offers_open: int
    open_requests: int
    todos: list[TodoOut]


@router.get('/owner/today', response=TodayOut)
def today_view(request):
    p = _prop(request)
    period = month_start(today())
    current = list(_current(p))
    total = Bed.objects.filter(room__property=p).count()
    unpaid = Invoice.objects.filter(booking__bed__room__property=p, period=period, status='open').count()
    offer_beds = Bed.objects.filter(room__property=p, offers_open=True).select_related('room')
    offers = Offer.objects.filter(bed__in=offer_beds, status='placed').count()
    open_t = Ticket.objects.filter(property=p, status__in=['Raised', 'Assigned']).count()
    todos = []
    for bed in offer_beds:
        n = Offer.objects.filter(bed=bed, status='placed').count()
        if n:
            todos.append({'key': f'offers-{bed.id}', 'text': f'{n} offer{"s" if n != 1 else ""} on Room {bed.room.number}, bed {bed.label}', 'label': 'Review', 'route': '/offers'})
    if open_t:
        todos.append({'key': 'tickets', 'text': f'{open_t} maintenance request{"s" if open_t != 1 else ""}', 'label': 'Open', 'route': '/tickets'})
    for b in Booking.objects.filter(bed__room__property=p, status__in=['confirmed', 'active'], agreement__tenant_signed_at__isnull=False,
                                    agreement__owner_signed_at__isnull=True).select_related('guest'):
        todos.append({'key': f'sign-{b.id}', 'text': f'{b.guest.name} signed the agreement. Your signature is next.', 'label': 'Sign', 'action': f'sign:{b.id}'})
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
            'offers_open': offers, 'open_requests': open_t, 'todos': todos}


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
                n = Offer.objects.filter(bed=bed, status='placed').count()
                cells.append({'bed_id': bed.id, 'label': bed.label, 'who': None, 'tag': 'offers' if bed.offers_open else 'free',
                              'note': f'{n} offer{"s" if n != 1 else ""}' if bed.offers_open else 'Free · listed'})
        full += all_full
        rooms.append({'number': room.number, 'full': all_full, 'beds': cells})
    return {'free': free, 'rooms': rooms, 'full_rooms': full}


# ---- offers -----------------------------------------------------------------------------------------------

class OwnerOfferOut(Schema):
    id: UUID
    name: str
    amount_paise: int
    months: int
    move_in_on: date
    verified: bool
    score: float | None
    past_stays: int


class OffersBoardOut(Schema):
    bed_id: int | None
    room: str | None
    bed: int | None
    listed_paise: int
    cap_paise: int
    closes_at: datetime | None
    open: bool
    accepted: str | None
    offers: list[OwnerOfferOut]


@router.get('/owner/offers', response=OffersBoardOut)
def offers(request):
    p = _prop(request)
    bed = (Bed.objects.filter(room__property=p, offers_open=True).select_related('room').first()
           or Bed.objects.filter(room__property=p, offers__status='accepted').select_related('room').order_by('-offers__decided_at').first())
    if not bed:
        return {'bed_id': None, 'room': None, 'bed': None, 'listed_paise': 0, 'cap_paise': 0, 'closes_at': None, 'open': False, 'accepted': None, 'offers': []}
    acc = Offer.objects.filter(bed=bed, status='accepted').select_related('tenant').order_by('-decided_at').first()
    items = []
    for o in Offer.objects.filter(bed=bed, status='placed').select_related('tenant').order_by('-amount_paise'):
        rec = svc.tenant_record(o.tenant)
        items.append({'id': o.id, 'name': o.tenant.name, 'amount_paise': o.amount_paise, 'months': o.months, 'move_in_on': o.move_in_on,
                      'verified': o.tenant.verified, 'score': rec['score'], 'past_stays': rec['past_stays']})
    return {'bed_id': bed.id, 'room': bed.room.number, 'bed': bed.label, 'listed_paise': bed.room.rent_paise,
            'cap_paise': offer_cap_paise(bed.room.rent_paise), 'closes_at': bed.offers_close_at, 'open': bed.offers_open,
            'accepted': acc.tenant.name if acc and not bed.offers_open else None, 'offers': items}


@router.post('/owner/offers/{offer_id}/accept', response=OffersBoardOut, summary='Accept one sealed offer; the rest are declined')
def accept(request, offer_id: UUID):
    p = _prop(request)
    o = Offer.objects.filter(pk=offer_id, bed__room__property=p).select_related('tenant', 'bed__room__property').first()
    if not o:
        raise ApiError(404, 'not_found', 'No such offer.')
    svc.accept_offer(o, request.party)
    return offers(request)


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


@router.post('/owner/residents/{booking_id}/sign', response=ResidentOut, summary="The owner's Aadhaar eSign")
def owner_sign(request, booking_id: UUID):
    b = _booking(request, booking_id)
    svc.sign_owner(b, request.party)
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


# ---- owner controls: offers on a bed, room rent ----------------------------------------------------------

class OffersToggleIn(Schema):
    open: bool


@router.post('/owner/beds/{bed_id}/offers', response=BoardOut, summary='Take sealed offers on a free bed (until Friday 6 pm), or stop')
def toggle_offers(request, bed_id: int, body: OffersToggleIn):
    p = _prop(request)
    bed = Bed.objects.filter(pk=bed_id, room__property=p).select_related('room').first()
    if not bed:
        raise ApiError(404, 'not_found', 'No such bed.')
    if body.open:
        from apps.property.services import free_beds
        with system():
            if bed.id not in {b.id for b in free_beds(p)}:
                raise ApiError(409, 'bed_not_free', 'Offers can only be taken on a bed that is free from the next move-in date.')
        svc.open_offers(bed)
    elif bed.offers_open:
        now = timezone.now()
        open_ = list(Offer.objects.filter(bed=bed, status='placed').select_related('tenant'))
        Offer.objects.filter(pk__in=[o.pk for o in open_]).update(status='declined', decided_at=now, updated_at=now)
        bed.offers_open = False
        bed.save(update_fields=['offers_open', 'updated_at'])
        from apps.core.api_support import notify
        for o in open_:
            notify(o.tenant, 'offer.declined', f'{p.name} stopped taking offers on that bed. You can book other beds at the listed rent.', org=p.organisation)
    from apps.core.api_support import audit
    audit(p.organisation, request.party, 'bed.offers_open' if body.open else 'bed.offers_closed', bed)
    return beds(request)


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
    if Bed.objects.filter(room=room, offers_open=True, offers__status='placed').exists():
        raise ApiError(409, 'offers_running', 'Close the offers on this room first: they were made against the current rent.')
    from apps.core.api_support import audit
    before = {'rent_paise': room.rent_paise}
    room.rent_paise = body.rent_paise
    room.save(update_fields=['rent_paise', 'updated_at'])
    audit(p.organisation, request.party, 'room.rent', room, before, {'rent_paise': body.rent_paise})
    return beds(request)
