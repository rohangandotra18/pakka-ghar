"""Owner API for applications: requests and bids (best first), accept, decline, and putting a room up for bids."""
from datetime import date, datetime
from uuid import UUID

from ninja import Router, Schema

from apps.booking.owner_dashboard.beds import BoardOut, beds
from apps.core.api_support import ApiError
from apps.property import services as property_svc

from .. import common
from ..models import Application
from . import services as svc

router = Router(tags=['owner'])


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
    fits = [] if a.room_id or a.status != 'pending' else [r.number for r in svc.rooms_that_fit(a.property, size, a.move_in_on, a.room_kind)]
    return {'id': a.id, 'room': a.room.number if a.room else None, 'room_kind': a.room_kind or (a.room.kind if a.room else ''),
            'amount_paise': a.amount_paise, 'rent_paise': a.amount_paise or (a.room.rent_paise if a.room else 0), 'months': a.months,
            'move_in_on': a.move_in_on, 'message': a.message, 'status': a.status, 'size': size, 'members': members, 'fits': fits,
            'created_at': a.created_at}


@router.get('/owner/applications', response=ApplicationsOut, summary='Requests to stay and bids, best bids first')
def applications(request):
    p = common.owner_property(request)
    from apps.property.services import offer_cap_paise
    bidding = []
    for r in p.rooms.filter(offers_open=True):
        bidding.append({'number': r.number, 'kind': r.get_kind_display(), 'rent_paise': r.rent_paise, 'cap_paise': offer_cap_paise(r.rent_paise),
                        'free': len(svc.free_in_room(r, property_svc.next_move_in())), 'closes_at': r.offers_close_at})
    live = Application.objects.filter(property=p, status='pending').select_related('room', 'property')
    order = sorted(live, key=lambda a: (a.amount_paise is None, -(a.amount_paise or 0), a.created_at))
    recent = Application.objects.filter(property=p, status__in=['accepted', 'declined']).select_related('room', 'property').order_by('-decided_at')[:10]
    return {'bidding': bidding, 'applications': [owner_application_out(a) for a in order], 'decided': [owner_application_out(a) for a in recent]}


def _app(request, app_id) -> Application:
    p = common.owner_property(request)
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


# ---- owner controls: a room up for bids, room rent, tour hours ------------------------------------------------

class BiddingIn(Schema):
    open: bool


@router.post('/owner/rooms/{number}/bidding', response=BoardOut, summary='Put a room up for bids until Friday 6 pm, or stop')
def toggle_bidding(request, number: str, body: BiddingIn):
    from apps.property.models import Room
    p = common.owner_property(request)
    room = Room.objects.filter(property=p, number=number).first()
    if not room:
        raise ApiError(404, 'not_found', f'No room {number}.')
    if body.open and not room.offers_open:
        svc.open_bidding(room, request.party)
    elif not body.open and room.offers_open:
        svc.close_bidding(room, request.party, reason=f'{p.name} stopped taking bids on Room {number}. You can apply at the listed rent.')
    return beds(request)
