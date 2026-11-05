"""Tenant side: tours, applications (with roommates and bids), booking a bed, the stay, notice, move-out, history."""
from datetime import date, datetime, timedelta
from uuid import UUID

from django.utils import timezone
from ninja import Router, Schema

from apps.core.api_support import IST, OPTIONAL, ApiError, idempotent, month_start, party_of, today
from apps.core.rls import system
from apps.payments import services as pay
from apps.payments.models import Invoice
from apps.property.models import MeterReading, Property

from . import services as svc
from .models import Application, ApplicationMember, Booking, Rating

router = Router(tags=['tenant'])


def _prop(slug: str) -> Property:
    p = Property.objects.filter(slug=slug).exclude(status='draft').first()
    if not p:
        raise ApiError(404, 'not_found', 'No such PG.')
    return p


class ListingRef(Schema):
    listing: str


# ---- tours ------------------------------------------------------------------------------------------------

class SlotsOut(Schema):
    slots: list[datetime]
    hours: dict


@router.get('/listings/{slug}/tour-slots', response=SlotsOut, auth=OPTIONAL, tags=['listings'], summary='Free tour times this week')
def tour_slots(request, slug: str):
    p = _prop(slug)
    return {'slots': svc.tour_slots(p), 'hours': svc.tour_hours(p)}


class TourIn(Schema):
    listing: str
    slot: datetime | None = None
    note: str = ''


class MyVisitOut(Schema):
    id: UUID
    listing: str
    name: str
    slot: datetime
    status: str
    note: str


def visit_out(v) -> dict:
    return {'id': v.id, 'listing': v.property.slug, 'name': v.property.name, 'slot': v.slot, 'status': v.status, 'note': v.note}


@router.get('/visits/mine', response=list[MyVisitOut], summary='Your tours, newest first')
def my_visits(request):
    from .models import Visit
    qs = Visit.objects.filter(tenant=party_of(request)).select_related('property').order_by('-created_at')
    return [visit_out(v) for v in qs]


@router.post('/visits/{visit_id}/cancel', response=MyVisitOut, summary='Cancel a tour you asked for')
def cancel_visit(request, visit_id: UUID):
    from apps.core.api_support import notify

    from .models import Visit
    v = Visit.objects.filter(pk=visit_id, tenant=party_of(request)).select_related('property').first()
    if not v:
        raise ApiError(404, 'not_found', 'No such tour.')
    if v.status in ('requested', 'confirmed'):
        v.status = 'cancelled'
        v.save(update_fields=['status', 'updated_at'])
        for o in svc.owners_of(v.organisation):
            notify(o, 'visit.cancelled', f'{request.party.first_name} cancelled their tour.', org=v.organisation)
    return visit_out(v)


@router.post('/visits', response=MyVisitOut, summary='Book a tour at one of the free times')
def visit(request, body: TourIn):
    party = party_of(request)
    v = svc.request_visit(party, _prop(body.listing), body.slot, body.note)
    return visit_out(v)


# ---- applications: to stay, with roommates, or a bid ---------------------------------------------------------

class ApplyIn(Schema):
    listing: str
    room: str = ''                  # a room number, or empty for any room (of room_kind, if given)
    room_kind: str = ''
    amount_paise: int | None = None  # a bid per bed, only for a room that is up for bids
    months: int = 11
    move_in_on: date | None = None
    message: str = ''
    roommates: list[str] = []       # their mobile numbers; each joins from their own app


class MemberOut(Schema):
    id: UUID
    name: str
    phone_last4: str
    is_lead: bool
    status: str
    verified: bool
    booking_id: UUID | None


class ApplicationOut(Schema):
    id: UUID
    listing: str
    name: str
    room: str | None
    room_kind: str
    amount_paise: int | None
    rent_paise: int
    months: int
    move_in_on: date
    message: str
    status: str
    decline_reason: str
    is_lead: bool
    members: list[MemberOut]
    count: int
    min_paise: int | None
    max_paise: int | None
    rank: int | None
    closes_at: datetime | None
    my_booking_id: UUID | None


def member_out(m) -> dict:
    p = m.party
    b = m.application.bookings.filter(guest_id=m.party_id).first() if m.party_id else None
    return {'id': m.id, 'name': (p.name if p else '') or 'Invited', 'phone_last4': m.phone[-4:], 'is_lead': m.is_lead,
            'status': m.status, 'verified': bool(p and p.verified), 'booking_id': b.id if b else None}


def application_out(a, me=None) -> dict:
    members = [member_out(m) for m in a.members.select_related('party', 'application')]
    mine = a.bookings.filter(guest=me).order_by('-created_at').first() if me else None
    room = a.room
    return {'id': a.id, 'listing': a.property.slug, 'name': a.property.name, 'room': room.number if room else None,
            'room_kind': a.room_kind or (room.kind if room else ''), 'amount_paise': a.amount_paise,
            'rent_paise': a.amount_paise or (room.rent_paise if room else 0), 'months': a.months, 'move_in_on': a.move_in_on,
            'message': a.message, 'status': a.status, 'decline_reason': a.decline_reason, 'is_lead': bool(me and a.lead_id == me.id),
            'members': members, **svc.standing(a), 'closes_at': room.offers_close_at if room and room.offers_open else None,
            'my_booking_id': mine.id if mine else None}


def _visible_application(party, app_id):
    """Applications the caller leads or is a member of (members read theirs with the system role, by seat)."""
    a = Application.objects.filter(pk=app_id, lead=party).select_related('property', 'room').first()
    if a:
        return a
    with system():
        if ApplicationMember.objects.filter(application_id=app_id, party=party).exists():
            return Application.objects.select_related('property', 'room').get(pk=app_id)
    raise ApiError(404, 'not_found', 'No such application.')


@router.post('/applications', response=ApplicationOut, summary='Apply to stay: a room or any room, alone or with roommates, at the rent or as a bid')
def create_application(request, body: ApplyIn):
    party = party_of(request)
    a = svc.apply(party, _prop(body.listing), room_number=body.room, room_kind=body.room_kind, amount_paise=body.amount_paise,
                  months=body.months, move_in=body.move_in_on, message=body.message, roommates=body.roommates)
    return application_out(a, party)


@router.get('/applications/mine', response=list[ApplicationOut], summary='Applications you made or joined')
def my_applications(request):
    party = party_of(request)
    with system():
        ids = set(ApplicationMember.objects.filter(party=party).exclude(status__in=['declined', 'left']).values_list('application_id', flat=True))
        apps = list(Application.objects.filter(pk__in=ids).select_related('property', 'room').order_by('-created_at'))
        return [application_out(a, party) for a in apps]


class ChangeIn(Schema):
    amount_paise: int | None = None
    months: int | None = None


@router.patch('/applications/{app_id}', response=ApplicationOut, summary='Change your bid or stay length')
def change_application(request, app_id: UUID, body: ChangeIn):
    party = party_of(request)
    a = svc.change_bid(_visible_application(party, app_id), party, body.amount_paise, body.months)
    return application_out(a, party)


@router.post('/applications/{app_id}/withdraw', response=ApplicationOut)
def withdraw_application(request, app_id: UUID):
    party = party_of(request)
    a = svc.withdraw(_visible_application(party, app_id), party)
    return application_out(a, party)


@router.post('/applications/{app_id}/members/{member_id}/remove', response=ApplicationOut, summary='Drop a roommate, or leave')
def remove_member(request, app_id: UUID, member_id: UUID):
    party = party_of(request)
    with system():
        a = svc.remove_member(_visible_application(party, app_id), party, member_id)
        return application_out(a, party)


class InviteOut(Schema):
    member_id: UUID
    application_id: UUID
    listing: str
    name: str
    from_name: str
    room: str | None
    amount_paise: int | None
    move_in_on: date
    months: int


@router.get('/invites', response=list[InviteOut], summary='Roommate invitations sent to your number')
def invites(request):
    out = []
    for m in svc.invites_for(party_of(request)):
        a = m.application
        out.append({'member_id': m.id, 'application_id': a.id, 'listing': a.property.slug, 'name': a.property.name,
                    'from_name': a.lead.name, 'room': a.room.number if a.room else None, 'amount_paise': a.amount_paise,
                    'move_in_on': a.move_in_on, 'months': a.months})
    return out


class AnswerIn(Schema):
    accept: bool


@router.post('/invites/{member_id}', response=ApplicationOut, summary='Join or turn down a roommate invitation')
def answer_invite(request, member_id: UUID, body: AnswerIn):
    party = party_of(request)
    a = svc.respond_invite(member_id, party, body.accept)
    with system():
        return application_out(a, party)


# ---- booking --------------------------------------------------------------------------------------------

class BookIn(Schema):
    listing: str
    months: int = 11


class AgreementOut(Schema):
    tenant_signed: bool
    owner_signed: bool
    stamped: bool
    certificate: str
    terms: dict


class BookingOut(Schema):
    id: UUID
    reference: str
    listing: str
    name: str
    area: str
    room: str
    bed: int
    status: str
    move_in_on: date
    months: int
    rent_paise: int
    deposit_paise: int
    hold_expires_at: datetime | None
    deposit_paid: bool
    agreement: AgreementOut
    police: str
    application_id: UUID | None


def booking_out(b: Booking) -> dict:
    prop, a = b.bed.room.property, b.agreement
    return {'id': b.id, 'reference': b.reference, 'listing': prop.slug, 'name': prop.name, 'area': prop.area,
            'room': b.bed.room.number, 'bed': b.bed.label, 'status': b.status,
            'move_in_on': b.stay_period.lower.astimezone(IST).date(), 'months': b.months, 'rent_paise': b.rent_paise,
            'deposit_paise': b.deposit_paise, 'hold_expires_at': b.hold_expires_at,
            'deposit_paid': b.payments.filter(purpose='deposit', status='captured').exists(),
            'agreement': {'tenant_signed': bool(a.tenant_signed_at), 'owner_signed': bool(a.owner_signed_at),
                          'stamped': bool(a.stamped_at), 'certificate': a.stamp_certificate, 'terms': a.terms},
            'police': b.police.status, 'application_id': b.application_id}


def _mine(request, booking_id) -> Booking:
    party = party_of(request)
    b = Booking.objects.filter(pk=booking_id, guest=party).select_related('bed__room__property', 'agreement', 'police').first()
    if not b:
        raise ApiError(404, 'not_found', 'No such booking.')
    return b


@router.post('/bookings', response=BookingOut, summary='Your held bed at this PG, after the owner accepted your application')
@idempotent
def book(request, body: BookIn):
    party = party_of(request)
    prop = _prop(body.listing)
    svc.expire_holds()
    with system():  # the hold the owner made when accepting
        held = Booking.objects.filter(guest=party, status__in=['hold', 'confirmed'], bed__room__property=prop).order_by('-created_at').first()
    if not held:
        raise ApiError(409, 'apply_first', 'Apply to stay first. The owner accepts, then you pay the deposit here.')
    return booking_out(Booking.objects.get(pk=held.pk))


@router.get('/bookings/{booking_id}', response=BookingOut)
def get_booking(request, booking_id: UUID):
    return booking_out(_mine(request, booking_id))


class PaymentOut(Schema):
    id: UUID
    order_id: str
    key_id: str
    provider: str
    purpose: str
    amount_paise: int
    status: str


def payment_out(p) -> dict:
    return {'id': p.id, 'order_id': p.provider_order_id, 'key_id': pay.gateway().key_id, 'provider': p.provider,
            'purpose': p.purpose, 'amount_paise': p.amount_paise, 'status': p.status}


@router.post('/bookings/{booking_id}/deposit', response=PaymentOut, summary='Start the deposit payment (UPI, into escrow)')
@idempotent
def deposit(request, booking_id: UUID):
    b = _mine(request, booking_id)
    svc.expire_holds()
    b.refresh_from_db()
    return payment_out(pay.create_payment(b, 'deposit'))


@router.post('/bookings/{booking_id}/stamp', response=BookingOut, summary='Pay stamp duty to the state and attach the e-stamp')
def do_stamp(request, booking_id: UUID):
    b = _mine(request, booking_id)
    svc.stamp(b, request.party)
    return booking_out(b)


@router.post('/bookings/{booking_id}/cancel', response=BookingOut)
def cancel(request, booking_id: UUID):
    b = _mine(request, booking_id)
    return booking_out(svc.cancel(b, request.party))


# ---- the stay -------------------------------------------------------------------------------------------

class InvoiceLineOut(Schema):
    kind: str
    description: str
    quantity: float
    rate_paise: int
    amount_paise: int
    tax_paise: int
    sac: str


class InvoiceOut(Schema):
    id: UUID
    number: str
    period: date
    due_on: date
    status: str
    total_paise: int
    paid_paise: int
    lines: list[InvoiceLineOut]


class MeterOut(Schema):
    model: str
    synced_at: datetime | None
    daily_kwh: list[float]
    units_14d: float
    tariff_paise: int


class StayOut(Schema):
    booking: BookingOut
    lat: float
    lng: float
    moved_in: bool
    since: str
    leaves_on: date | None
    autopay: bool
    bill: InvoiceOut | None
    first_due_on: date | None
    meter: MeterOut | None
    receipts: int


class StayEnvelope(Schema):
    stay: StayOut | None


def current_booking(party) -> Booking | None:
    svc.activate_started()
    return (Booking.objects.filter(guest=party, status__in=['confirmed', 'active']).select_related('bed__room__property', 'agreement', 'police')
            .order_by('-created_at').first())


def _meter(b: Booking) -> dict | None:
    room = b.bed.room
    meter = getattr(room, 'meter', None)
    if not meter:
        return None
    since = timezone.now() - timedelta(days=15)
    reads = list(MeterReading.objects.filter(meter=meter, read_at__gte=since).order_by('read_at'))
    with system():  # the room's meter is shared: count everyone living in it
        sharers = max(1, Booking.objects.filter(bed__room=room, status='active').count())
    daily = [round(float(b2.kwh_total - a2.kwh_total) / sharers, 1) for a2, b2 in zip(reads, reads[1:])][-14:]
    return {'model': meter.model, 'synced_at': reads[-1].read_at if reads else None, 'daily_kwh': daily,
            'units_14d': round(sum(daily), 1), 'tariff_paise': room.property.tariff_paise}


def stay_out(b: Booking) -> dict:
    prop = b.bed.room.property
    moved = b.status == 'active'
    bill = None
    if moved:
        period = month_start(today())
        with system():  # the monthly charge job, run on demand if it hasn't yet
            inv = pay.charge_month(Booking.objects.get(pk=b.pk), period)
        bill = pay.invoice_out(Invoice.objects.get(pk=inv.pk))
    since, _ = svc.stay_label(b)
    return {'booking': booking_out(b), 'lat': float(prop.lat or 0), 'lng': float(prop.lng or 0), 'moved_in': moved, 'since': since,
            'leaves_on': svc.leaves_on(b), 'autopay': b.autopay, 'bill': bill,
            'first_due_on': None if moved else b.stay_period.lower.astimezone(IST).date() + timedelta(days=4),
            'meter': _meter(b) if moved else None,
            'receipts': b.payments.filter(status='captured').count()}


@router.get('/stay', response=StayEnvelope, summary='The current stay: bill, meter, agreement, deposit')
def stay(request):
    b = current_booking(party_of(request))
    return {'stay': stay_out(b) if b else None}


def _stay_or_404(request) -> Booking:
    b = current_booking(party_of(request))
    if not b:
        raise ApiError(404, 'no_stay', 'You have no current stay.')
    return b


@router.post('/stay/pay', response=PaymentOut, summary="Pay this month's bill by UPI")
@idempotent
def pay_bill(request):
    b = _stay_or_404(request)
    inv = Invoice.objects.filter(booking=b, status='open').order_by('period').first()
    return payment_out(pay.create_payment(b, 'invoice', inv, method='upi_autopay' if b.autopay else 'upi'))


class AutopayIn(Schema):
    on: bool


@router.put('/stay/autopay', response=StayEnvelope, summary='UPI AutoPay mandate on the 1st of each month')
def autopay(request, body: AutopayIn):
    b = _stay_or_404(request)
    b.autopay = body.on
    b.save(update_fields=['autopay', 'updated_at'])
    return {'stay': stay_out(b)}


@router.post('/stay/notice', response=StayEnvelope, summary='Give one month of notice')
def notice(request):
    b = _stay_or_404(request)
    svc.give_notice(b, request.party)
    return {'stay': stay_out(b)}


class EndIn(Schema):
    aspects: dict[str, int]
    deposit_on_time: bool | None = None
    comment: str = ''


class HistoryItem(Schema):
    booking_id: UUID | None
    name: str
    area: str
    from_label: str
    to_label: str
    rent_paise: int
    current: bool
    rated: float | None
    deposit: str


class HistoryOut(Schema):
    items: list[HistoryItem]
    score: float | None
    rated_by: int


def history_out(party) -> dict:
    items = []
    qs = Booking.objects.filter(guest=party, status__in=['confirmed', 'active', 'ended']).select_related('bed__room__property').order_by('-stay_period')
    mine = {r.booking_id: r for r in Rating.objects.filter(tenant=party, direction='tenant_to_pg')}
    for b in qs:
        p = b.bed.room.property
        frm, to = svc.stay_label(b)
        r = mine.get(b.id)
        items.append({'booking_id': b.id, 'name': p.name, 'area': f'{p.area}, {p.get_city_display()}',
                      'from_label': frm, 'to_label': to, 'rent_paise': b.rent_paise, 'current': b.status in ('confirmed', 'active'),
                      'rated': float(r.score) if r else None, 'deposit': b.deposit_outcome})
    rec = svc.tenant_record(party)
    return {'items': items, 'score': rec['score'], 'rated_by': rec['rated_by']}


@router.post('/stay/end', response=HistoryOut, summary='Rate the stay and move out; the deposit refund starts')
def end(request, body: EndIn):
    b = _stay_or_404(request)
    svc.end_and_rate(b, request.party, body.aspects, body.deposit_on_time, body.comment)
    return history_out(request.party)


@router.get('/history', response=HistoryOut, summary='Every stay through Pakka Ghar, and the owners’ rating of you')
def history(request):
    return history_out(party_of(request))

