"""Tenant side: visits, sealed offers, booking a bed, the current stay, notice, move-out, history."""
from datetime import date, datetime, timedelta
from uuid import UUID

from django.utils import timezone
from ninja import Router, Schema

from apps.core.api_support import IST, ApiError, idempotent, month_start, party_of, today
from apps.core.rls import system
from apps.payments import services as pay
from apps.payments.models import Invoice
from apps.property.models import Bed, MeterReading, Property

from . import services as svc
from .models import Booking, Offer, Rating

router = Router(tags=['tenant'])


def _prop(slug: str) -> Property:
    p = Property.objects.filter(slug=slug).exclude(status='draft').first()
    if not p:
        raise ApiError(404, 'not_found', 'No such PG.')
    return p


class ListingRef(Schema):
    listing: str


class VisitOut(Schema):
    id: UUID
    slot: datetime


class MyVisitOut(Schema):
    id: UUID
    listing: str
    name: str
    slot: datetime
    status: str


@router.get('/visits/mine', response=list[MyVisitOut], summary='Your visit requests, newest first')
def my_visits(request):
    from .models import Visit
    qs = Visit.objects.filter(tenant=party_of(request)).select_related('property').order_by('-created_at')
    return [{'id': v.id, 'listing': v.property.slug, 'name': v.property.name, 'slot': v.slot, 'status': v.status} for v in qs]


@router.post('/visits/{visit_id}/cancel', response=MyVisitOut, summary='Cancel a visit you asked for')
def cancel_visit(request, visit_id: UUID):
    from .models import Visit
    v = Visit.objects.filter(pk=visit_id, tenant=party_of(request)).select_related('property').first()
    if not v:
        raise ApiError(404, 'not_found', 'No such visit.')
    if v.status in ('requested', 'confirmed'):
        v.status = 'cancelled'
        v.save(update_fields=['status', 'updated_at'])
        for o in svc.owners_of(v.organisation):
            from apps.core.api_support import notify
            notify(o, 'visit.cancelled', f'{request.party.first_name} cancelled their visit.', org=v.organisation)
    return {'id': v.id, 'listing': v.property.slug, 'name': v.property.name, 'slot': v.slot, 'status': v.status}


@router.post('/visits', response=VisitOut, summary='Ask to visit; the owner confirms in the app')
def visit(request, body: ListingRef):
    party = party_of(request)
    v = svc.request_visit(party, _prop(body.listing))
    return {'id': v.id, 'slot': v.slot}


# ---- offers ---------------------------------------------------------------------------------------------

class OfferIn(Schema):
    listing: str
    amount_paise: int
    months: int = 11


class OfferOut(Schema):
    id: UUID
    listing: str
    name: str
    room: str
    bed: int
    listed_paise: int
    cap_paise: int
    amount_paise: int
    months: int
    move_in_on: date
    status: str
    closes_at: datetime | None
    count: int
    min_paise: int | None
    max_paise: int | None
    rank: int | None
    booking_id: UUID | None


def offer_out(o: Offer) -> dict:
    bed, prop = o.bed, o.bed.room.property
    st = svc.offer_standing(o) if o.status == 'placed' else {'count': 0, 'min_paise': None, 'max_paise': None, 'rank': None}
    from apps.property.services import offer_cap_paise
    b = getattr(o, 'booking', None)
    return {'id': o.id, 'listing': prop.slug, 'name': prop.name, 'room': bed.room.number, 'bed': bed.label,
            'listed_paise': bed.room.rent_paise, 'cap_paise': offer_cap_paise(bed.room.rent_paise),
            'amount_paise': o.amount_paise, 'months': o.months, 'move_in_on': o.move_in_on, 'status': o.status,
            'closes_at': bed.offers_close_at, **st, 'booking_id': b.id if b else None}


@router.get('/offers/mine', response=list[OfferOut])
def my_offers(request):
    party = party_of(request)
    qs = Offer.objects.filter(tenant=party).exclude(status='withdrawn').select_related('bed__room__property').order_by('-created_at')
    return [offer_out(o) for o in qs]


@router.post('/offers', response=OfferOut, summary='Place or change a sealed offer (listed rent to +15%)')
def place_offer(request, body: OfferIn):
    party = party_of(request)
    prop = _prop(body.listing)
    bed = Bed.objects.filter(room__property=prop, offers_open=True).select_related('room__property').first()
    if not bed:
        raise ApiError(409, 'offers_closed', 'This PG is not taking offers. Book at the listed rent instead.')
    return offer_out(svc.place_offer(party, bed, body.amount_paise, body.months))


@router.delete('/offers/{offer_id}', response=OfferOut)
def withdraw(request, offer_id: UUID):
    party = party_of(request)
    o = Offer.objects.filter(pk=offer_id, tenant=party).first()
    if not o:
        raise ApiError(404, 'not_found', 'No such offer.')
    return offer_out(svc.withdraw_offer(o, party))


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
    offer_id: UUID | None


def booking_out(b: Booking) -> dict:
    prop, a = b.bed.room.property, b.agreement
    return {'id': b.id, 'reference': b.reference, 'listing': prop.slug, 'name': prop.name, 'area': prop.area,
            'room': b.bed.room.number, 'bed': b.bed.label, 'status': b.status,
            'move_in_on': b.stay_period.lower.astimezone(IST).date(), 'months': b.months, 'rent_paise': b.rent_paise,
            'deposit_paise': b.deposit_paise, 'hold_expires_at': b.hold_expires_at,
            'deposit_paid': b.payments.filter(purpose='deposit', status='captured').exists(),
            'agreement': {'tenant_signed': bool(a.tenant_signed_at), 'owner_signed': bool(a.owner_signed_at),
                          'stamped': bool(a.stamped_at), 'certificate': a.stamp_certificate, 'terms': a.terms},
            'police': b.police.status, 'offer_id': b.offer_id}


def _mine(request, booking_id) -> Booking:
    party = party_of(request)
    b = Booking.objects.filter(pk=booking_id, guest=party).select_related('bed__room__property', 'agreement', 'police').first()
    if not b:
        raise ApiError(404, 'not_found', 'No such booking.')
    return b


@router.post('/bookings', response=BookingOut, summary='Hold a bed for 10 minutes while the deposit is paid')
@idempotent
def book(request, body: BookIn):
    party = party_of(request)
    prop = _prop(body.listing)
    from apps.property.services import free_beds, next_move_in
    with system():  # an accepted offer's hold comes back even after offers have closed
        held = Booking.objects.filter(guest=party, status='hold', bed__room__property=prop).first()
    if held:
        return booking_out(Booking.objects.get(pk=held.pk))
    with system():  # availability spans other people's bookings
        beds = [b for b in free_beds(prop) if not b.offers_open]
    if not beds:
        raise ApiError(409, 'no_free_bed', 'No bed is free to book at the listed rent. Make an offer, or try another PG.')
    key, fp = request.idempotency
    b = svc.create_hold(party, beds[0], next_move_in(), body.months, key, fp)
    return booking_out(b)


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


@router.post('/bookings/{booking_id}/sign', response=BookingOut, summary='Aadhaar eSign by the resident')
def sign(request, booking_id: UUID):
    b = _mine(request, booking_id)
    svc.sign_tenant(b, request.party)
    return booking_out(b)


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

