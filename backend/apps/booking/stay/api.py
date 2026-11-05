"""Tenant API for the stay: bill, meter, AutoPay, notice, move-out, and past stays."""
from datetime import date, datetime, timedelta
from uuid import UUID

from django.utils import timezone
from ninja import Router, Schema

from apps.booking.bookings.api import BookingOut, PaymentOut, booking_out, payment_out
from apps.core.api_support import IST, ApiError, idempotent, month_start, party_of, today
from apps.core.rls import system
from apps.payments import services as pay
from apps.payments.models import Invoice
from apps.property.models import MeterReading

from ..applications import services as applications_svc
from ..bookings import services as bookings_svc
from ..models import Booking, Rating
from . import services as svc

router = Router(tags=['tenant'])


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
    bookings_svc.activate_started()
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
    rec = applications_svc.tenant_record(party)
    return {'items': items, 'score': rec['score'], 'rated_by': rec['rated_by']}


@router.post('/stay/end', response=HistoryOut, summary='Rate the stay and move out; the deposit refund starts')
def end(request, body: EndIn):
    b = _stay_or_404(request)
    svc.end_and_rate(b, request.party, body.aspects, body.deposit_on_time, body.comment)
    return history_out(request.party)


@router.get('/history', response=HistoryOut, summary='Every stay through Pakka Ghar, and the owners’ rating of you')
def history(request):
    return history_out(party_of(request))
