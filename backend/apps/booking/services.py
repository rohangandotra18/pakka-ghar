"""Offers, holds, bookings, agreements, police verification, notice, move-out and ratings."""
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
from apps.property.models import Bed, Property
from apps.property.services import next_move_in, offer_cap_paise

from .models import BLOCKING, Agreement, Booking, Offer, PoliceVerification, Rating, Visit

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
                offer: Offer | None = None, hold_for: timedelta | None = None) -> Booking:
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
    rent = offer.amount_paise if offer else bed.room.rent_paise
    now = timezone.now()
    try:
        with transaction.atomic():
            b = Booking.objects.create(
                organisation=bed.organisation, reference='PG-' + secrets.token_hex(4).upper(), bed=bed, guest=party,
                status='hold', stay_period=DateTimeTZRange(ist(move_in), ist(add_months(move_in, months))),
                hold_expires_at=now + (hold_for or timedelta(minutes=settings.HOLD_MINUTES)), months=months,
                rent_paise=rent, deposit_paise=bed.room.rent_paise * prop.deposit_months,  # an offer never raises the deposit
                offer=offer, idempotency_key=key, request_fingerprint=fp)
    except IntegrityError as e:
        if 'exclude_space_double_booking' in str(e):
            raise ApiError(409, 'bed_taken', 'Someone has just booked that bed. Pick another.')
        raise
    b.refresh_from_db()
    Agreement.objects.create(organisation=b.organisation, booking=b, tenant=party, terms=_terms(b))
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


# ---- offers ----------------------------------------------------------------------------------------------

def place_offer(party: Party, bed: Bed, amount_paise: int, months: int) -> Offer:
    require_verified(party)
    if not bed.offers_open or (bed.offers_close_at and bed.offers_close_at < timezone.now()):
        raise ApiError(409, 'offers_closed', 'Offers are closed on this bed. Book it at the listed rent instead.')
    with system():
        if Booking.objects.filter(guest=party, status__in=['confirmed', 'active']).exists():
            raise ApiError(409, 'already_booked', 'You already have a booking. Cancel it or move out before making offers.')
    rent = bed.room.rent_paise
    cap = offer_cap_paise(rent)
    if not rent <= amount_paise <= cap:
        raise ApiError(422, 'offer_out_of_range', f'Offers go from ₹{rent // 100:,} to ₹{cap // 100:,} (15% over the listed rent).')
    if months not in (6, 9, 11):
        raise ApiError(422, 'bad_months', 'Choose 6, 9 or 11 months.')
    o = Offer.objects.filter(bed=bed, tenant=party, status='placed').first()
    if o:
        before = {'amount_paise': o.amount_paise, 'months': o.months}
        o.amount_paise, o.months = amount_paise, months
        o.save(update_fields=['amount_paise', 'months', 'updated_at'])
        audit(o.organisation, party, 'offer.change', o, before, {'amount_paise': amount_paise, 'months': months})
        return o
    o = Offer.objects.create(organisation=bed.organisation, bed=bed, tenant=party, amount_paise=amount_paise,
                             months=months, move_in_on=next_move_in())
    audit(o.organisation, party, 'offer.place', o, after={'amount_paise': amount_paise, 'months': months})
    for ow in owners_of(o.organisation):
        notify(ow, 'offer.new', f'New offer on Room {bed.room.number}, bed {bed.label}.', org=o.organisation, offer=str(o.id))
    return o


def withdraw_offer(o: Offer, party: Party) -> Offer:
    if o.status != 'placed':
        raise ApiError(409, 'not_open', 'This offer is no longer open.')
    o.status, o.decided_at = 'withdrawn', timezone.now()
    o.save(update_fields=['status', 'decided_at', 'updated_at'])
    audit(o.organisation, party, 'offer.withdraw', o)
    return o


def tenant_record(party: Party) -> dict:
    """The rental record owners see with an offer: past stays and the owners' revealed ratings."""
    with system():
        from apps.property.services import revealed
        cutoff = timezone.now() - timedelta(days=settings.RATING_REVEAL_DAYS)
        agg = revealed(Rating.objects.filter(tenant=party, direction='owner_to_tenant'), cutoff).aggregate(a=Avg('score'), n=Count('id'))
        stays = Booking.objects.filter(guest=party, status='ended').count()
    return {'score': round(float(agg['a']), 1) if agg['a'] is not None else None, 'rated_by': agg['n'], 'past_stays': stays}


def offer_standing(o: Offer) -> dict:
    """What a tenant may know about a sealed round: how many offers, their range, and roughly where theirs sits."""
    with system():
        amounts = sorted((x.amount_paise for x in Offer.objects.filter(bed_id=o.bed_id, status='placed')), reverse=True)
    rank = amounts.index(o.amount_paise) + 1 if o.amount_paise in amounts else None
    return {'count': len(amounts), 'min_paise': amounts[-1] if amounts else None, 'max_paise': amounts[0] if amounts else None, 'rank': rank}


@transaction.atomic
def accept_offer(o: Offer, actor: Party) -> Booking:
    if o.status != 'placed':
        raise ApiError(409, 'not_open', 'This offer is no longer open.')
    if not o.tenant.verified:
        raise ApiError(409, 'tenant_unverified', "This person hasn't verified their ID yet.")
    bed = Bed.objects.select_for_update().get(pk=o.bed_id)
    now = timezone.now()
    o.status, o.decided_at = 'accepted', now
    o.save(update_fields=['status', 'decided_at', 'updated_at'])
    others = list(Offer.objects.filter(bed=bed, status='placed').exclude(pk=o.pk).select_related('tenant'))
    Offer.objects.filter(pk__in=[x.pk for x in others]).update(status='declined', decided_at=now, updated_at=now)
    bed.offers_open = False
    bed.save(update_fields=['offers_open', 'updated_at'])
    b = create_hold(o.tenant, bed, o.move_in_on, o.months, key=f'offer-{o.id}', fp=f'offer-{o.id}', offer=o,
                    hold_for=timedelta(hours=settings.OFFER_HOLD_HOURS))
    audit(o.organisation, actor, 'offer.accept', o, after={'booking': b.reference})
    name = bed.room.property.name
    notify(o.tenant, 'offer.accepted', f'{name} accepted your offer. Pay the deposit within 24 hours to hold the bed.', org=o.organisation, booking=str(b.id))
    for x in others:
        notify(x.tenant, 'offer.declined', f'{name} chose another offer. Similar PGs nearby are open.', org=o.organisation)
    return b


def open_offers(bed: Bed) -> Bed:
    """Take sealed offers on a scarce bed until Friday 6 pm."""
    bed.offers_open, bed.offers_close_at = True, next_friday_6pm()
    bed.save(update_fields=['offers_open', 'offers_close_at', 'updated_at'])
    return bed


# ---- visits ----------------------------------------------------------------------------------------------

def request_visit(party: Party, prop: Property) -> Visit:
    pending = Visit.objects.filter(property=prop, tenant=party, status__in=['requested', 'confirmed'], slot__gte=timezone.now()).first()
    if pending:  # asking twice doesn't book two visits
        return pending
    t = today()
    sat = t + timedelta(days=(5 - t.weekday()) % 7 or 7)
    v = Visit.objects.create(organisation=prop.organisation, property=prop, tenant=party, slot=ist(sat, 11))
    for o in owners_of(prop.organisation):
        notify(o, 'visit.new', f'{party.first_name} asked to visit on Saturday at 11 am.', org=prop.organisation, visit=str(v.id))
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
