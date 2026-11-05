"""Tenant API for applications and roommate invites."""
from datetime import date, datetime
from uuid import UUID

from ninja import Router, Schema

from apps.core.api_support import ApiError, party_of
from apps.core.rls import system

from .. import common
from ..models import Application, ApplicationMember
from . import services as svc

router = Router(tags=['tenant'])


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
    a = svc.apply(party, common.listing_by_slug(body.listing), room_number=body.room, room_kind=body.room_kind, amount_paise=body.amount_paise,
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
