"""Applications (with roommates and bids), holds, bookings, agreements, tours, police verification, notice, move-out and ratings."""
import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.core.api_support import ApiError, add_months, audit, ist, month_label, next_friday_6pm, notify, require_verified, today
from apps.core.ledger import post
from apps.core.models import Membership, Party
from apps.core.rls import system
from apps.jurisdiction.rules import MissingFields, build_packet
from apps.property.models import Bed, Property, Room
from apps.property.services import next_move_in, offer_cap_paise

from .models import BLOCKING, Agreement, Application, ApplicationMember, Booking, PoliceVerification, Rating, Visit

ASPECTS = ('Cleanliness', 'Food', 'Owner response', 'Value')


def owners_of(org) -> list[Party]:
    return [m.party for m in Membership.objects.filter(organisation=org, role__in=['owner', 'manager']).select_related('party')]


def expire_holds() -> int:
    """Release holds whose time ran out, so they stop blocking the bed, and tell each tenant. Also runs every
    minute in Celery."""
    with system():
        lapsed = list(Booking.objects.select_for_update(of=('self',)).filter(status='hold', hold_expires_at__lt=timezone.now())
                      .select_related('guest', 'bed__room__property'))
        if not lapsed:
            return 0
        Booking.objects.filter(pk__in=[b.pk for b in lapsed]).update(status='expired', updated_at=timezone.now())
    for b in lapsed:
        name = b.bed.room.property.name
        notify(b.guest, 'booking.expired', f'Your hold on {name} ran out before the deposit was paid. Book again if the bed is still free.', org=b.organisation)
    return len(lapsed)


def activate_started() -> None:
    """A confirmed booking becomes a live stay on its move-in date (only rows the caller can see)."""
    Booking.objects.filter(status='confirmed', stay_period__startswith__lte=timezone.now()).update(status='active', updated_at=timezone.now())


def _terms(b: Booking) -> dict:
    p = b.bed.room.property
    return {'property': p.name, 'address': p.address, 'room': b.bed.room.number, 'bed': b.bed.label,
            'start': b.stay_period.lower.date().isoformat() if hasattr(b.stay_period, 'lower') else str(b.stay_period[0].date()),
            'months': b.months, 'rent_paise': b.rent_paise, 'deposit_paise': b.deposit_paise,
            'notice_months': p.notice_months, 'tariff_paise': p.tariff_paise, 'payment': 'In the Pakka Ghar app only. No cash.'}


def create_hold(party: Party, bed: Bed, move_in: date, months: int, key: str, fp: str,
                application: Application | None = None, rent_paise: int | None = None, hold_for: timedelta | None = None) -> Booking:
    require_verified(party)
    if months not in (6, 9, 11):
        raise ApiError(422, 'bad_months', 'Choose 6, 9 or 11 months.')
    expire_holds()
    prop = bed.room.property
    with system():  # the guest's bookings with every owner, not just this one
        mine = list(Booking.objects.filter(guest=party, status__in=BLOCKING).select_related('bed__room'))
    for b in mine:
        if b.status == 'hold' and b.bed.room.property_id == prop.id:
            return b  # already holding a bed here (e.g. from an accepted offer)
        if b.status != 'hold':
            raise ApiError(409, 'already_booked', 'You already have a booking. End that stay before booking another.')
        with system():
            Booking.objects.filter(pk=b.pk).update(status='cancelled', updated_at=timezone.now())
    rent = rent_paise or bed.room.rent_paise
    now = timezone.now()
    try:
        with transaction.atomic():
            b = Booking.objects.create(
                organisation=bed.organisation, reference='PG-' + secrets.token_hex(4).upper(), bed=bed, guest=party,
                status='hold', stay_period=DateTimeTZRange(ist(move_in), ist(add_months(move_in, months))),
                hold_expires_at=now + (hold_for or timedelta(minutes=settings.HOLD_MINUTES)), months=months,
                rent_paise=rent, deposit_paise=bed.room.rent_paise * prop.deposit_months,  # a bid never raises the deposit
                application=application, idempotency_key=key, request_fingerprint=fp)
    except IntegrityError as e:
        if 'exclude_space_double_booking' in str(e):
            raise ApiError(409, 'bed_taken', 'Someone has just booked that bed. Pick another.')
        raise
    b.refresh_from_db()
    ag = Agreement.objects.create(organisation=b.organisation, booking=b, tenant=party, terms=_terms(b))
    from .agreements import build_document
    with system():  # reads the owner's template and both names
        build_document(Agreement.objects.select_related('booking__bed__room__property', 'booking__guest').get(pk=ag.pk))
    PoliceVerification.objects.create(organisation=b.organisation, booking=b, tenant=party, jurisdiction=prop.city)
    audit(b.organisation, party, 'booking.hold', b, after={'bed': bed.id, 'rent_paise': rent})
    return b


def cancel(b: Booking, actor: Party) -> Booking:
    """Cancel before move-in. A paid deposit is reversed with contra-entries, never deleted."""
    if b.status not in ('hold', 'confirmed'):
        raise ApiError(409, 'cannot_cancel', 'Only a booking that has not started can be cancelled.')
    from apps.core.ledger import reverse
    for pay in b.payments.filter(purpose='deposit', status='captured', journal__isnull=False):
        with system():  # the owner's books: posting needs the system role when a resident cancels
            reverse(pay.journal, f'Deposit refunded on cancelling {b.reference}')
        pay.status = 'refunded'
        pay.save(update_fields=['status', 'updated_at'])
    b.status = 'cancelled'
    b.save(update_fields=['status', 'updated_at'])
    audit(b.organisation, actor, 'booking.cancel', b)
    return b


# ---- agreement ------------------------------------------------------------------------------------------

def sign_tenant(b: Booking, party: Party) -> Agreement:
    if b.status not in ('confirmed', 'active'):
        raise ApiError(409, 'pay_deposit_first', 'Pay the deposit before signing.')
    a = b.agreement
    if not a.tenant_signed_at:
        a.tenant_signed_at = timezone.now()
        a.esign_ref = 'ESIGN-' + secrets.token_hex(5).upper()
        a.save(update_fields=['tenant_signed_at', 'esign_ref', 'updated_at'])
        for o in owners_of(b.organisation):
            notify(o, 'agreement.sign', f'{party.first_name} signed the agreement. Sign it to finish the booking.', org=b.organisation, booking=str(b.id))
    return a


def sign_owner(b: Booking, party: Party) -> Agreement:
    a = b.agreement
    if not a.tenant_signed_at:
        raise ApiError(409, 'tenant_signs_first', 'The resident signs first.')
    if not a.owner_signed_at:
        a.owner_signed_at = timezone.now()
        a.save(update_fields=['owner_signed_at', 'updated_at'])
        notify(b.guest, 'agreement.signed', 'The owner signed your agreement. Pay the stamp duty to finish.', org=b.organisation, booking=str(b.id))
    return a


def stamp(b: Booking, party: Party) -> Agreement:
    a = b.agreement
    if not (a.tenant_signed_at and a.owner_signed_at):
        raise ApiError(409, 'not_signed', 'Both of you sign before the e-stamp.')
    if not a.stamped_at:
        a.stamped_at = timezone.now()
        a.stamp_certificate = 'IN-' + b.bed.room.property.city[:2].upper() + secrets.token_hex(6).upper()
        a.save(update_fields=['stamped_at', 'stamp_certificate', 'updated_at'])
        prepare_police(b)
    return a


# ---- police verification ---------------------------------------------------------------------------------

def _packet_inputs(b: Booking) -> tuple[dict, dict]:
    t, p = b.guest, b.bed.room.property
    prof = t.profile or {}
    works = t.works_at or ''
    owner = next(iter(owners_of(b.organisation)), None)
    tenant = {
        'full_name': t.name, 'father_or_guardian_name': prof.get('guardian_name'), 'date_of_birth': prof.get('date_of_birth'),
        'mobile': t.phone, 'permanent_address': prof.get('home_address'), 'previous_address': prof.get('home_address'),
        'emergency_contact': prof.get('emergency_contact'), 'id_type': 'Aadhaar' if t.aadhaar_masked else None,
        'id_last4': t.aadhaar_masked[-4:] if t.aadhaar_masked else None, 'photo': 'selfie on file' if t.selfie_matched_at else None,
        'occupation': 'Student' if any(w in works for w in ('University', 'College', 'Institute', 'School')) else ('Working' if works else None),
        'workplace_or_college': works, 'move_in_on': b.stay_period.lower.date().isoformat(),
    }
    owner_d = {'owner_name': owner.name if owner else None, 'owner_mobile': owner.phone if owner else None,
               'property_address': p.address, 'room_number': b.bed.room.number}
    return tenant, owner_d


def prepare_police(b: Booking) -> PoliceVerification:
    pv = b.police
    tenant, owner = _packet_inputs(b)
    try:
        pv.packet = build_packet(pv.jurisdiction, tenant, owner)
    except MissingFields as e:
        pv.packet = {'missing': e.missing}
    pv.save(update_fields=['packet', 'updated_at'])
    return pv


def submit_police(b: Booking, actor: Party) -> PoliceVerification:
    pv = prepare_police(b)
    if 'missing' in pv.packet:
        raise ApiError(422, 'police_form_incomplete', 'The police form still needs: ' + ', '.join(pv.packet['missing']).replace('_', ' ') + '.')
    if pv.status == 'not_started':
        pv.status, pv.submitted_at = 'submitted', timezone.now()
        pv.save(update_fields=['status', 'submitted_at', 'updated_at'])
        audit(b.organisation, actor, 'police.submit', pv)
    return pv


def mark_police_verified(b: Booking, actor: Party) -> PoliceVerification:
    """A person confirms the police cleared the resident; the app never decides this on its own."""
    pv = b.police
    if pv.status != 'submitted':
        raise ApiError(409, 'submit_first', 'Submit the verification first.')
    pv.status, pv.verified_at, pv.verified_by = 'verified', timezone.now(), actor
    pv.save(update_fields=['status', 'verified_at', 'verified_by', 'updated_at'])
    audit(b.organisation, actor, 'police.verified', pv)
    notify(b.guest, 'police.verified', 'Your police verification is complete.', org=b.organisation)
    return pv


# ---- applications: alone or with roommates, at the listed rent or as a bid ----------------------------------

MAX_ROOMMATES = 2   # a triple room is the largest


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


def _rooms_that_fit(prop: Property, size: int, start: date, kind: str = '', exclude_bidding: bool = True) -> list[Room]:
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
        if not _rooms_that_fit(prop, size, move_in, room_kind):
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
    if a.status == 'pending':
        _tell_owners_new(a)
    return a


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


def withdraw(a: Application, party: Party) -> Application:
    if a.lead_id != party.id:
        raise ApiError(403, 'not_lead', 'Only the person who applied can withdraw it. You can leave it instead.')
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
        _tell_owners_new(a)


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
def accept(a: Application, actor: Party, room_number: str = '') -> list[Booking]:
    if a.status != 'pending':
        raise ApiError(409, 'not_open', 'This application isn’t waiting for you.')
    members = [m for m in a.members.select_related('party') if m.status == 'joined']
    for m in members:
        if not m.party.verified:
            raise ApiError(409, 'tenant_unverified', f'{m.party.first_name} hasn’t verified their ID yet.')
    size = len(members)
    room = a.room
    if not room:
        fits = _rooms_that_fit(a.property, size, a.move_in_on, a.room_kind)
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
        notify(m.party, 'application.accepted', f'{a.property.name} accepted your application: Room {room.number}, bed {b.bed.label}. Pay your deposit within 24 hours.',
               org=a.organisation, booking=str(b.id))
    if room.offers_open and len(beds) == size:  # the room is full now: bidding ends, the other bids are declined
        close_bidding(room, actor, reason=f'{a.property.name} accepted another bid on Room {room.number}.')
    audit(a.organisation, actor, 'application.accept', a, after={'room': room.number, 'bookings': [b.reference for b in bookings]})
    return bookings


def decline(a: Application, actor: Party, reason: str = '') -> Application:
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
    room.save(update_fields=['offers_open', 'offers_close_at', 'updated_at'])
    audit(room.organisation, actor, 'room.bidding_open', room)
    return room


def close_bidding(room: Room, actor: Party, reason: str = '') -> Room:
    open_bids = list(Application.objects.filter(room=room, status__in=['forming', 'pending'], amount_paise__isnull=False))
    for a in open_bids:
        decline(a, actor, reason or f'Bidding on Room {room.number} has closed.')
    room.offers_open = False
    room.save(update_fields=['offers_open', 'updated_at'])
    audit(room.organisation, actor, 'room.bidding_closed', room)
    return room


# ---- tours ------------------------------------------------------------------------------------------------

TOUR_DEFAULT = {'days': [0, 1, 2, 3, 4, 5], 'start': '10:00', 'end': '18:00', 'minutes': 30}


def tour_hours(prop: Property) -> dict:
    return {**TOUR_DEFAULT, **(prop.attributes or {}).get('tour_hours', {})}


def tour_slots(prop: Property, days: int = 7) -> list:
    """Free tour times in the owner's tour hours, from two hours from now, one tour per slot."""
    h = tour_hours(prop)
    sh, sm = map(int, h['start'].split(':'))
    eh, em = map(int, h['end'].split(':'))
    step = timedelta(minutes=int(h['minutes']))
    earliest = timezone.now() + timedelta(hours=2)
    with system():
        booked = set(Visit.objects.filter(property=prop, status__in=['requested', 'confirmed'], slot__gte=timezone.now()).values_list('slot', flat=True))
    out = []
    for i in range(days + 1):
        d = today() + timedelta(days=i)
        if d.weekday() not in h['days']:
            continue
        t, end = ist(d, sh, sm), ist(d, eh, em)
        while t + step <= end:
            if t >= earliest and t not in booked:
                out.append(t)
            t += step
    return out


def request_visit(party: Party, prop: Property, slot=None, note: str = '') -> Visit:
    pending = Visit.objects.filter(property=prop, tenant=party, status__in=['requested', 'confirmed'], slot__gte=timezone.now()).first()
    if pending:  # one upcoming tour per PG; reschedule by cancelling it
        return pending
    slots = tour_slots(prop)
    if slot is None:
        if not slots:
            raise ApiError(409, 'no_slots', 'No tour times are free this week. Message the owner instead.')
        slot = slots[0]
    elif slot not in slots:
        raise ApiError(409, 'slot_taken', 'That time isn’t free any more. Pick another.')
    v = Visit.objects.create(organisation=prop.organisation, property=prop, tenant=party, slot=slot, note=note.strip()[:200])
    when = slot.astimezone(ist(today()).tzinfo).strftime('%a %-d %b, %-I:%M %p').replace('AM', 'am').replace('PM', 'pm')
    for o in owners_of(prop.organisation):
        notify(o, 'visit.new', f'{party.first_name} asked for a tour on {when}.', org=prop.organisation, visit=str(v.id))
    return v


# ---- living there --------------------------------------------------------------------------------------

def give_notice(b: Booking, party: Party) -> Booking:
    if b.status != 'active':
        raise ApiError(409, 'not_living_here', 'You can give notice once you have moved in.')
    if b.notice_given_on:
        return b
    t = today()
    leave = t + timedelta(days=30 * b.bed.room.property.notice_months)
    b.notice_given_on = t
    b.stay_period = DateTimeTZRange(b.stay_period.lower, ist(leave))
    b.save(update_fields=['notice_given_on', 'stay_period', 'updated_at'])
    audit(b.organisation, party, 'booking.notice', b, after={'leaves_on': leave.isoformat()})
    for o in owners_of(b.organisation):
        notify(o, 'booking.notice', f'{party.first_name} gave notice and leaves on {leave:%-d %B}.', org=b.organisation, booking=str(b.id))
    return b


def leaves_on(b: Booking) -> date | None:
    return b.stay_period.upper.astimezone(ist(today()).tzinfo).date() if b.notice_given_on and b.stay_period.upper else None


def end_and_rate(b: Booking, party: Party, aspects: dict[str, int], deposit_on_time: bool | None, comment: str) -> Booking:
    if b.status not in ('active', 'confirmed'):
        raise ApiError(409, 'no_stay', 'There is no stay to end.')
    if set(aspects) != set(ASPECTS) or not all(1 <= int(v) <= 5 for v in aspects.values()):
        raise ApiError(422, 'rate_all', 'Rate all four, from 1 to 5 stars.')
    score = Decimal(sum(int(v) for v in aspects.values()) / len(aspects)).quantize(Decimal('0.1'))
    Rating.objects.create(organisation=b.organisation, booking=b, tenant=party, direction='tenant_to_pg',
                          aspects=aspects, score=score, comment=comment[:2000], deposit_on_time=deposit_on_time)
    now = timezone.now()
    b.status = 'ended' if b.stay_period.lower <= now else 'cancelled'
    b.ended_on = today()
    b.stay_period = DateTimeTZRange(b.stay_period.lower, max(now, b.stay_period.lower + timedelta(seconds=1)))
    b.deposit_outcome = 'Deposit refund in progress'
    b.autopay = False
    b.save(update_fields=['status', 'ended_on', 'stay_period', 'deposit_outcome', 'autopay', 'updated_at'])
    audit(b.organisation, party, 'booking.end', b, after={'score': str(score)})
    for o in owners_of(b.organisation):
        notify(o, 'booking.ended', f'{party.first_name} moved out. Settle the deposit and rate them.', org=b.organisation, booking=str(b.id))
    return b


def settle_deposit(b: Booking, actor: Party, deduction_paise: int = 0, reason: str = '') -> Booking:
    """Return the deposit from escrow, less any deduction the owner explains."""
    if b.status not in ('ended', 'cancelled'):
        raise ApiError(409, 'still_living_here', 'Settle the deposit after the resident moves out.')
    from apps.core.ledger import balance
    held = -balance(b.organisation, 'deposit_liability', b.guest)
    if held <= 0:
        raise ApiError(409, 'nothing_held', 'No deposit is held for this resident.')
    if not 0 <= deduction_paise <= held or (deduction_paise and not reason.strip()):
        raise ApiError(422, 'bad_deduction', 'A deduction needs a reason and cannot exceed the deposit.')
    refund = held - deduction_paise
    # The whole deposit leaves escrow and the liability closes; a deduction goes to the owner's bank as income.
    lines = [('deposit_liability', b.guest, held), ('escrow', None, -held),
             ('bank', None, deduction_paise), ('deductions_income', None, -deduction_paise)]
    post(b.organisation, 'deposit_settled', f'Deposit settled for {b.reference}', lines, ref=b.reference)
    days = (today() - (b.ended_on or today())).days
    b.deposit_outcome = (f'₹{deduction_paise // 100:,} kept for {reason.strip()}' if deduction_paise
                         else f'Returned in {max(days, 1)} day{"s" if max(days, 1) != 1 else ""}')
    b.save(update_fields=['deposit_outcome', 'updated_at'])
    audit(b.organisation, actor, 'deposit.settle', b, after={'refund_paise': refund, 'deduction_paise': deduction_paise})
    notify(b.guest, 'deposit.settled', f'Your deposit of ₹{refund // 100:,} is on its way back.', org=b.organisation)
    return b


def owner_rates(b: Booking, actor: Party, score: int, comment: str = '') -> Rating:
    if b.status not in ('ended', 'cancelled'):
        raise ApiError(409, 'still_living_here', 'Rate the resident after they move out.')
    if not 1 <= score <= 5:
        raise ApiError(422, 'bad_score', 'Give 1 to 5 stars.')
    r, _ = Rating.objects.get_or_create(booking=b, direction='owner_to_tenant', defaults={
        'organisation': b.organisation, 'tenant': b.guest, 'score': Decimal(score), 'comment': comment, 'aspects': {}})
    return r


def stay_label(b: Booking) -> tuple[str, str]:
    lo = b.stay_period.lower.astimezone(ist(today()).tzinfo).date()
    to = 'now' if b.status in ('active', 'confirmed') else month_label(b.ended_on or b.stay_period.upper.date())
    return month_label(lo), to
