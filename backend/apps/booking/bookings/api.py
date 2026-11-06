"""Tenant API for a booking: the held bed, deposit into escrow, e-stamp, cancel."""
from datetime import date, datetime
from uuid import UUID

from ninja import Router, Schema

from apps.core.api_support import IST, ApiError, idempotent, party_of
from apps.core.rls import system
from apps.payments import services as pay

from .. import common
from ..police.services import police_missing
from ..models import Booking
from . import services as svc

router = Router(tags=['tenant'])


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
    police_missing: list[str]   # details the resident still has to add for the police form
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
            'police': b.police.status, 'police_missing': police_missing(b) if b.police.status == 'not_started' else [],
            'application_id': b.application_id}


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
    prop = common.listing_by_slug(body.listing)
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
