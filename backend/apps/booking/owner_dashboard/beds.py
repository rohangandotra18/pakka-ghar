"""Owner API: the bed board and room rent."""
from django.utils import timezone
from ninja import Router, Schema

from apps.core.api_support import IST, ApiError

from .. import common
from ..models import Application
from ..stay import services as stay_svc

router = Router(tags=['owner'])


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
    p = common.owner_property(request)
    now = timezone.now()
    rooms, full, free = [], 0, 0
    for room in p.rooms.prefetch_related('beds'):
        cells, all_full = [], True
        for bed in room.beds.all():
            cur = bed.bookings.filter(status='active', stay_period__contains=now).select_related('guest').first()
            nxt = bed.bookings.filter(status__in=['confirmed', 'hold'], stay_period__startswith__gt=now).select_related('guest').order_by('stay_period').first()
            if cur and cur.notice_given_on:
                all_full = False
                cells.append({'bed_id': bed.id, 'label': bed.label, 'who': cur.guest.first_name, 'tag': 'leaving', 'note': f'leaves {stay_svc.leaves_on(cur):%-d %b}'})
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


class RentIn(Schema):
    rent_paise: int


@router.patch('/owner/rooms/{number}', response=BoardOut, summary="Change a room's rent per bed (applies to new bookings only)")
def room_rent(request, number: str, body: RentIn):
    from apps.property.models import Room
    p = common.owner_property(request)
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
