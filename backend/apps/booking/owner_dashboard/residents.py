"""Owner API: residents, their record, police steps and move-out."""
from datetime import date
from uuid import UUID

from ninja import Router, Schema

from apps.core.api_support import ApiError
from apps.core.ledger import balance

from .. import common
from ..models import Booking
from ..police import services as police_svc
from ..stay import services as stay_svc

router = Router(tags=['owner'])


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
    p = common.owner_property(request)
    cur = Booking.objects.filter(bed__room__property=p, status__in=['active', 'confirmed'])
    past = Booking.objects.filter(bed__room__property=p, status='ended')
    qs = (cur if tab == 'current' else past).select_related('guest', 'bed__room', 'police')
    qs = qs.order_by('bed__room__number', 'bed__label') if tab == 'current' else qs.order_by('-ended_on')
    items = []
    for b in qs:
        frm, to = stay_svc.stay_label(b)
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
    frm, _ = stay_svc.stay_label(b)
    agreement = ('Signed · e-stamped' if a.stamped_at else 'Signed by both' if a.owner_signed_at else
                 'Waiting for your signature' if a.tenant_signed_at else 'Not signed yet')
    return {'booking_id': b.id, 'name': b.guest.name, 'phone': b.guest.phone, 'room': b.bed.room.number, 'status': b.status,
            'identity': 'Aadhaar verified' if b.guest.verified else 'Not verified', 'police': pv.get_status_display(),
            'police_missing': [m.replace('_', ' ') for m in (pv.packet or {}).get('missing', [])],
            'agreement': agreement, 'rent_paise': b.rent_paise, 'autopay': b.autopay, 'deposit_paise': b.deposit_paise,
            'deposit_held_paise': -balance(b.organisation, 'deposit_liability', b.guest), 'deposit_outcome': b.deposit_outcome,
            'since': frm, 'leaves_on': stay_svc.leaves_on(b)}


def _booking(request, booking_id) -> Booking:
    p = common.owner_property(request)
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
    police_svc.submit_police(b, request.party)
    return resident_out(b)


@router.post('/owner/residents/{booking_id}/police/verified', response=ResidentOut, summary='Record that the police cleared the resident')
def police_verified(request, booking_id: UUID):
    b = _booking(request, booking_id)
    police_svc.mark_police_verified(b, request.party)
    return resident_out(b)


class SettleIn(Schema):
    deduction_paise: int = 0
    reason: str = ''
    rating: int | None = None


@router.post('/owner/residents/{booking_id}/move-out', response=ResidentOut, summary='Settle the deposit and rate the resident')
def move_out(request, booking_id: UUID, body: SettleIn):
    b = _booking(request, booking_id)
    stay_svc.settle_deposit(b, request.party, body.deduction_paise, body.reason)
    if body.rating:
        stay_svc.owner_rates(b, request.party, body.rating)
    return resident_out(b)
