"""Requests to stay: alone or with roommates, at the rent or as a sealed bid (up to +15%); accepting holds beds."""
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.booking.bookings.services import create_hold
from apps.booking.common import owners_of
from apps.core.api_support import ApiError, add_months, audit, ist, next_friday_6pm, notify, require_verified, today
from apps.core.models import Party
from apps.core.rls import system
from apps.property.models import Bed, Property, Room
from apps.property.services import next_move_in, offer_cap_paise

from ..models import BLOCKING, Application, ApplicationMember, Booking, Rating

# ---- applications: alone or with roommates, at the listed rent or as a bid ----------------------------------

MAX_ROOMMATES = 2   # a triple room is the largest
MAX_OPEN_REQUESTS = 5   # live requests one tenant may lead at once; each one notifies and waits on an owner


def tenant_record(party: Party) -> dict:
    """The rental record owners see with an application: past stays and the owners' revealed ratings."""
    with system():
        from apps.property.services import revealed
        cutoff = timezone.now() - timedelta(days=settings.RATING_REVEAL_DAYS)
        agg = revealed(Rating.objects.filter(tenant=party, direction='owner_to_tenant'), cutoff).aggregate(a=Avg('score'), n=Count('id'))
        stays = Booking.objects.filter(guest=party, status='ended').count()
    return {'score': round(float(agg['a']), 1) if agg['a'] is not None else None, 'rated_by': agg['n'], 'past_stays': stays}


def free_in_room(room: Room, start: date) -> list[Bed]:
    """Beds in this room with nothing booked for a month from `start`. Spans everyone's bookings: system role."""
    lo, hi = ist(start), ist(add_months(start, 1))
    with system():
        taken = set(Booking.objects.filter(bed__room=room, status__in=BLOCKING, stay_period__overlap=(lo, hi)).values_list('bed_id', flat=True))
        return [b for b in Bed.objects.filter(room=room).select_related('room').order_by('label') if b.id not in taken]


def _no_live_booking(party: Party) -> None:
    with system():
        if Booking.objects.filter(guest=party, status__in=['confirmed', 'active']).exists():
            raise ApiError(409, 'already_booked', 'You already have a booking. Cancel it or move out before applying elsewhere.')


def _check_bid(room: Room, amount_paise: int | None) -> None:
    if room.offers_open:
        if room.offers_close_at and room.offers_close_at < timezone.now():
            raise ApiError(409, 'bids_closed', 'Bidding on this room has closed.')
        cap = offer_cap_paise(room.rent_paise)
        if amount_paise is None or not room.rent_paise <= amount_paise <= cap:
            raise ApiError(422, 'bid_out_of_range', f'Room {room.number} is up for bids: bid from ₹{room.rent_paise // 100:,} to ₹{cap // 100:,} a bed (15% over the rent).')
    elif amount_paise is not None:
        raise ApiError(422, 'not_bidding', f'Room {room.number} isn’t up for bids. Apply at the listed rent.')


def rooms_that_fit(prop: Property, size: int, start: date, kind: str = '', exclude_bidding: bool = True) -> list[Room]:
    rooms = Room.objects.filter(property=prop).order_by('number')
    if kind:
        rooms = rooms.filter(kind=kind)
    if exclude_bidding:
        rooms = rooms.filter(offers_open=False)
    return [r for r in rooms if len(free_in_room(r, start)) >= size]


def apply(lead: Party, prop: Property, *, room_number: str = '', room_kind: str = '', amount_paise: int | None = None,
          months: int = 11, move_in: date | None = None, message: str = '', roommates: list[str] = ()) -> Application:
    from apps.identity.services import normalise_phone
    require_verified(lead)
    _no_live_booking(lead)
    if months not in (6, 9, 11):
        raise ApiError(422, 'bad_months', 'Choose 6, 9 or 11 months.')
    move_in = move_in or next_move_in()
    if move_in < today() or move_in > today() + timedelta(days=120):
        raise ApiError(422, 'bad_move_in', 'Pick a move-in date in the next four months.')
    phones = []
    for raw in roommates:
        ph = normalise_phone(raw)
        if ph == lead.phone:
            raise ApiError(422, 'roommate_is_you', 'Add your roommate’s number, not yours.')
        if ph not in phones:
            phones.append(ph)
    if len(phones) > MAX_ROOMMATES:
        raise ApiError(422, 'too_many', 'You can apply with up to two roommates.')
    size = 1 + len(phones)
    if Application.objects.filter(property=prop, lead=lead, status__in=['forming', 'pending']).exists():
        raise ApiError(409, 'already_applied', 'You already have an application here. Change or withdraw it instead.')
    with system():   # across every owner: the tenant's own requests elsewhere are not this owner's rows
        open_now = Application.objects.filter(lead=lead, status__in=['forming', 'pending']).count()
    if open_now >= MAX_OPEN_REQUESTS:
        raise ApiError(409, 'too_many_requests', f'You have {open_now} requests waiting. Withdraw one, or wait for an answer, before sending another.')
    room = None
    if room_number:
        room = Room.objects.filter(property=prop, number=room_number).first()
        if not room:
            raise ApiError(404, 'no_room', f'No room {room_number}.')
        _check_bid(room, amount_paise)
        if len(free_in_room(room, move_in)) < size:
            raise ApiError(409, 'not_enough_beds', f'Room {room.number} doesn’t have {size} free bed{"s" if size > 1 else ""} then.')
    else:
        if amount_paise is not None:
            raise ApiError(422, 'pick_room', 'Pick the room you’re bidding on.')
        if not rooms_that_fit(prop, size, move_in, room_kind):
            raise ApiError(409, 'not_enough_beds', f'No room here has {size} free bed{"s" if size > 1 else ""} together then. Try another date or PG.')
    a = Application.objects.create(organisation=prop.organisation, property=prop, room=room, room_kind=room_kind if not room else '',
                                   lead=lead, amount_paise=amount_paise, months=months, move_in_on=move_in, message=message.strip()[:500],
                                   status='forming' if phones else 'pending')
    ApplicationMember.objects.create(organisation=prop.organisation, application=a, phone=lead.phone, party=lead, is_lead=True,
                                     status='joined', joined_at=timezone.now())
    for ph in phones:
        ApplicationMember.objects.create(organisation=prop.organisation, application=a, phone=ph)
        with system():
            mate = Party.objects.filter(phone=ph).first()
        if mate:
            notify(mate, 'invite.new', f'{lead.first_name} wants you as a roommate at {prop.name}. Accept in the app.', org=prop.organisation, application=str(a.id))
    audit(a.organisation, lead, 'application.create', a, after={'size': size, 'bid': amount_paise})
    if a.status == 'pending' and not _try_instant(a):
        _tell_owners_new(a)
    a.refresh_from_db()
    return a


def _try_instant(a: Application) -> bool:
    """On a room with instant booking on, a ready request is accepted straight away and signed with the owner's
    standing consent, so the tenant can sign and pay in one sitting. Returns whether it was accepted."""
    if a.status != 'pending' or a.amount_paise is not None:
        return False
    size = a.members.filter(status='joined').count()
    candidates = [a.room] if a.room else rooms_that_fit(a.property, size, a.move_in_on, a.room_kind)
    room = next((r for r in candidates if r and r.instant_book and not r.offers_open and r.instant_by_id and r.instant_consent), None)
    if not room:
        return False
    with system():
        owner = next((o for o in owners_of(a.organisation) if o.id == room.instant_by_id), None)
    if not owner:      # whoever switched it on no longer runs this PG
        return False
    from types import SimpleNamespace

    from ..agreements.signing import record_signature
    from ..models import Agreement
    try:
        with transaction.atomic(), system():   # accepted on the owner's behalf, inside the tenant's own request
            for b in accept(a, owner, '' if a.room else room.number, instant=True):
                ag = Agreement.objects.select_related('booking').get(booking=b)
                record_signature(ag, owner, 'owner', SimpleNamespace(id=room.instant_consent), ag.pages, None, 'Instant booking (standing consent)')
    except ApiError:
        return False   # e.g. the beds went meanwhile: it waits for the owner as usual
    who = a.lead.first_name + (f' and {size - 1} roommate{"s" if size > 2 else ""}' if size > 1 else '')
    for o in owners_of(a.organisation):
        notify(o, 'application.instant', f'{who} booked Room {room.number} with instant booking. They sign and pay next.',
               org=a.organisation, application=str(a.id))
    return True


def set_instant(room: Room, actor: Party, on: bool, challenge_id=None, code: str = '') -> Room:
    """Switch instant booking on (with the owner's code, which stands as their signature on each instant
    acceptance) or off."""
    from apps.property.models import PayoutAccount
    if on:
        if room.offers_open:
            raise ApiError(409, 'bidding_on', f'Room {room.number} is up for bids. Stop the bidding first.')
        if not PayoutAccount.objects.filter(organisation=room.organisation).exists():
            raise ApiError(409, 'payout_first', 'Add the bank account rent is paid into first.')
        from ..agreements.signing import use_code
        ch = use_code(actor, challenge_id, code)
        room.instant_book, room.instant_by, room.instant_consent = True, actor, ch.id
    else:
        room.instant_book, room.instant_by, room.instant_consent = False, None, None
    room.save(update_fields=['instant_book', 'instant_by', 'instant_consent', 'updated_at'])
    audit(room.organisation, actor, 'room.instant_on' if on else 'room.instant_off', room)
    return room


def _tell_owners_new(a: Application) -> None:
    n = a.members.filter(status='joined').count()
    what = f'bid ₹{a.amount_paise // 100:,} a bed on Room {a.room.number}' if a.is_bid else f'applied to stay{f" in Room {a.room.number}" if a.room else ""}'
    who = a.lead.first_name + (f' and {n - 1} roommate{"s" if n > 2 else ""}' if n > 1 else '')
    for o in owners_of(a.organisation):
        notify(o, 'application.new', f'{who} {what}.', org=a.organisation, application=str(a.id))


def change_bid(a: Application, party: Party, amount_paise: int | None, months: int | None) -> Application:
    if a.lead_id != party.id or a.status not in ('forming', 'pending'):
        raise ApiError(409, 'not_open', 'This application can’t be changed now.')
    if amount_paise is not None:
        if not a.room:
            raise ApiError(422, 'not_bidding', 'This application isn’t a bid.')
        _check_bid(a.room, amount_paise)
        a.amount_paise = amount_paise
    if months is not None:
        if months not in (6, 9, 11):
            raise ApiError(422, 'bad_months', 'Choose 6, 9 or 11 months.')
        a.months = months
    a.save(update_fields=['amount_paise', 'months', 'updated_at'])
    audit(a.organisation, party, 'application.change', a, after={'amount_paise': a.amount_paise, 'months': a.months})
    return a


def _lock(a: Application) -> Application:
    """Lock the request's row and read its status afresh. The owner accepting or declining and the tenant
    withdrawing can land at the same moment; whichever comes second waits here and then sees what the first did,
    so a request is never both accepted (beds held) and withdrawn."""
    a.status = Application.objects.select_for_update(of=('self',)).values_list('status', flat=True).get(pk=a.pk)
    return a


def withdraw(a: Application, party: Party) -> Application:
    if a.lead_id != party.id:
        raise ApiError(403, 'not_lead', 'Only the person who applied can withdraw it. You can leave it instead.')
    _lock(a)
    if a.status not in ('forming', 'pending'):
        raise ApiError(409, 'not_open', 'This application is no longer open.')
    a.status, a.decided_at = 'withdrawn', timezone.now()
    a.save(update_fields=['status', 'decided_at', 'updated_at'])
    for m in a.members.exclude(party=party).filter(status='joined').select_related('party'):
        notify(m.party, 'application.withdrawn', f'{party.first_name} withdrew your application to {a.property.name}.', org=a.organisation)
    audit(a.organisation, party, 'application.withdraw', a)
    return a


def invites_for(party: Party) -> list[ApplicationMember]:
    """Roommate invitations sent to this person's phone number (found by number, so the system role reads them)."""
    with system():
        return list(ApplicationMember.objects.filter(phone=party.phone, status='invited', application__status='forming')
                    .select_related('application__property', 'application__lead', 'application__room'))


def respond_invite(member_id, party: Party, accept: bool) -> Application:
    with system():
        m = ApplicationMember.objects.select_related('application__property', 'application__lead').filter(
            pk=member_id, phone=party.phone, status='invited', application__status='forming').first()
        if not m:
            raise ApiError(404, 'not_found', 'This invitation is no longer open.')
        a = m.application
        if accept:
            require_verified(party)
            _no_live_booking(party)
            m.party, m.status, m.joined_at = party, 'joined', timezone.now()
        else:
            m.status = 'declined'
        m.save(update_fields=['party', 'status', 'joined_at', 'updated_at'])
        notify(a.lead, 'invite.answered', f'{party.first_name} {"joined" if accept else "said no to"} your application to {a.property.name}.', org=a.organisation)
        _maybe_ready(a)
        audit(a.organisation, party, 'invite.accept' if accept else 'invite.decline', m)
        return a


def remove_member(a: Application, party: Party, member_id) -> Application:
    """The lead drops someone who said no or hasn't answered; a joined roommate can remove themselves."""
    m = a.members.filter(pk=member_id).exclude(is_lead=True).first()
    if not m or (a.lead_id != party.id and m.party_id != party.id):
        raise ApiError(404, 'not_found', 'No such roommate on this application.')
    if a.status not in ('forming', 'pending'):
        raise ApiError(409, 'not_open', 'This application is no longer open.')
    m.status = 'left'
    m.save(update_fields=['status', 'updated_at'])
    _maybe_ready(a)
    return a


def _maybe_ready(a: Application) -> None:
    """Goes to the owner once everyone on it has joined. A roommate who said no keeps it waiting until the lead drops
    them: the lead asked to live with that person, so it never turns into a solo application on its own."""
    live = [m for m in a.members.all() if m.status in ('invited', 'joined', 'declined')]
    if a.status == 'forming' and live and all(m.status == 'joined' for m in live):
        a.status = 'pending'
        a.save(update_fields=['status', 'updated_at'])
        if not _try_instant(a):
            _tell_owners_new(a)


def refresh_after_leaving(a: Application) -> None:
    """Someone left (or closed their account): if everyone still on it has joined, it now goes to the owner."""
    a.refresh_from_db()
    _maybe_ready(a)


def standing(a: Application) -> dict:
    """For a bid: how many bids on the room, their range, and where this one sits. Bids are sealed: no names."""
    if not (a.is_bid and a.room_id):
        return {'count': 0, 'min_paise': None, 'max_paise': None, 'rank': None}
    with system():
        amounts = sorted(Application.objects.filter(room_id=a.room_id, status__in=['forming', 'pending'], amount_paise__isnull=False)
                         .values_list('amount_paise', flat=True), reverse=True)
    rank = amounts.index(a.amount_paise) + 1 if a.amount_paise in amounts else None
    return {'count': len(amounts), 'min_paise': amounts[-1] if amounts else None, 'max_paise': amounts[0] if amounts else None, 'rank': rank}


@transaction.atomic
def accept(a: Application, actor: Party, room_number: str = '', instant: bool = False) -> list[Booking]:
    _lock(a)
    if a.status != 'pending':
        raise ApiError(409, 'not_open', 'This application isn’t waiting for you.')
    if a.property.status != 'published':
        raise ApiError(409, 'paused', f'{a.property.name} is paused, so it can’t take new tenants. Contact the trust team.')
    members = [m for m in a.members.select_related('party') if m.status == 'joined']
    for m in members:
        if not m.party.verified:
            raise ApiError(409, 'tenant_unverified', f'{m.party.first_name} hasn’t verified their ID yet.')
    size = len(members)
    room = a.room
    if not room:
        fits = rooms_that_fit(a.property, size, a.move_in_on, a.room_kind)
        room = next((r for r in fits if r.number == room_number), None) if room_number else (fits[0] if fits else None)
        if not room:
            raise ApiError(409, 'not_enough_beds', f'No room has {size} free bed{"s" if size > 1 else ""} together for {a.move_in_on:%-d %b}.')
    room = Room.objects.select_for_update().get(pk=room.pk)
    beds = free_in_room(room, a.move_in_on)
    if len(beds) < size:
        raise ApiError(409, 'not_enough_beds', f'Room {room.number} no longer has {size} free beds.')
    rent = a.amount_paise or room.rent_paise
    bookings = [create_hold(m.party, bed, a.move_in_on, a.months, key=f'app-{a.id}-{m.id}', fp=f'app-{a.id}', application=a,
                            rent_paise=rent, hold_for=timedelta(hours=settings.OFFER_HOLD_HOURS))
                for m, bed in zip(members, beds)]
    now = timezone.now()
    a.status, a.decided_at, a.room = 'accepted', now, room
    a.save(update_fields=['status', 'decided_at', 'room', 'updated_at'])
    for m, b in zip(members, bookings):
        ApplicationMember.objects.filter(pk=m.pk).update(updated_at=now)
        notify(m.party, 'application.accepted', (f'Instant booking at {a.property.name}: Room {room.number}, bed {b.bed.label} is held for you. Sign and pay the deposit to book it.' if instant else
               f'{a.property.name} accepted you and signed: Room {room.number}, bed {b.bed.label}. Sign and pay the deposit within 24 hours to book it.'),
               org=a.organisation, booking=str(b.id))
    if room.offers_open and len(beds) == size:  # the room is full now: bidding ends, the other bids are declined
        close_bidding(room, actor, reason=f'{a.property.name} accepted another bid on Room {room.number}.')
    audit(a.organisation, actor, 'application.accept', a, after={'room': room.number, 'bookings': [b.reference for b in bookings]})
    return bookings


def decline(a: Application, actor: Party, reason: str = '') -> Application:
    _lock(a)
    if a.status not in ('forming', 'pending'):
        raise ApiError(409, 'not_open', 'This application is no longer open.')
    a.status, a.decided_at, a.decline_reason = 'declined', timezone.now(), reason.strip()[:200]
    a.save(update_fields=['status', 'decided_at', 'decline_reason', 'updated_at'])
    for m in a.members.filter(status='joined').select_related('party'):
        notify(m.party, 'application.declined', f'{a.property.name} said no{": " + a.decline_reason if a.decline_reason else ""}. Similar PGs nearby are open.', org=a.organisation)
    audit(a.organisation, actor, 'application.decline', a, after={'reason': a.decline_reason})
    return a


def open_bidding(room: Room, actor: Party) -> Room:
    """Put a room up for bids until Friday 6 pm. It needs a free bed; applications at the listed rent stop for it."""
    if not free_in_room(room, next_move_in()):
        raise ApiError(409, 'room_full', f'Room {room.number} has no free bed to bid on.')
    room.offers_open, room.offers_close_at = True, next_friday_6pm()
    room.instant_book, room.instant_by, room.instant_consent = False, None, None   # bids and instant booking don't mix
    room.save(update_fields=['offers_open', 'offers_close_at', 'instant_book', 'instant_by', 'instant_consent', 'updated_at'])
    audit(room.organisation, actor, 'room.bidding_open', room)
    return room


def announce_ended_bidding() -> int:
    """Tell the owners of each room whose bidding deadline has passed that it's time to pick a bid: until they do,
    the room takes neither bids nor requests. Told once per deadline (the notification itself is the record), so
    the job can run as often as it likes. Call with the system role. Returns how many rooms were announced."""
    from apps.core.models import Notification
    n = 0
    for room in Room.objects.filter(offers_open=True, offers_close_at__lt=timezone.now()).select_related('property__organisation'):
        stamp = room.offers_close_at.isoformat()
        if Notification.objects.filter(kind='bidding.ended', data__room=str(room.id), data__closes_at=stamp).exists():
            continue
        bids = Application.objects.filter(room=room, status__in=['forming', 'pending'], amount_paise__isnull=False).count()
        title = (f'Bidding on Room {room.number} has ended with {bids} bid{"" if bids == 1 else "s"}. Pick one to fill the bed.' if bids
                 else f'Bidding on Room {room.number} ended with no bids. Stop it to take requests at the listed rent again.')
        for o in owners_of(room.property.organisation):
            notify(o, 'bidding.ended', title, org=room.property.organisation, room=str(room.id), closes_at=stamp)
        n += 1
    return n


def close_bidding(room: Room, actor: Party, reason: str = '') -> Room:
    open_bids = list(Application.objects.filter(room=room, status__in=['forming', 'pending'], amount_paise__isnull=False))
    for a in open_bids:
        decline(a, actor, reason or f'Bidding on Room {room.number} has closed.')
    room.offers_open = False
    room.save(update_fields=['offers_open', 'updated_at'])
    audit(room.organisation, actor, 'room.bidding_closed', room)
    return room
