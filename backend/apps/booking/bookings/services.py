"""A held bed becomes a booking: the 24-hour hold, cancelling, releasing expired holds, the e-stamp."""
import secrets
from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from apps.booking.common import owners_of
from apps.booking.police.services import prepare_police
from apps.core.api_support import ApiError, add_months, audit, ist, notify, require_verified
from apps.core.models import Party
from apps.core.rls import system
from apps.property.models import Bed

from ..models import BLOCKING, Agreement, Application, Booking, PoliceVerification


def expire_holds() -> int:
    """Release holds whose time ran out, so they stop blocking the bed, and tell each tenant. Also runs every
    minute in Celery."""
    with system():
        lapsed = list(Booking.objects.select_for_update(of=('self',)).filter(status='hold', hold_expires_at__lt=timezone.now())
                      .select_related('guest', 'bed__room__property', 'organisation'))
        if not lapsed:
            return 0
        Booking.objects.filter(pk__in=[b.pk for b in lapsed]).update(status='expired', updated_at=timezone.now())
    for b in lapsed:
        name = b.bed.room.property.name
        notify(b.guest, 'booking.expired', f'Your hold on {name} ran out before the deposit was paid. Book again if the bed is still free.', org=b.organisation)
        with system():
            owners = owners_of(b.organisation)
        for o in owners:   # the owner held this bed for them; now it's free again
            notify(o, 'booking.expired', f'{b.guest.first_name} didn’t pay the deposit in time: Room {b.bed.room.number}, bed {b.bed.label} is free again.',
                   org=b.organisation, booking=str(b.id))
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
        with system():  # only one hold at a time: the older one, at another PG, goes back to its owner
            Booking.objects.filter(pk=b.pk).update(status='cancelled', updated_at=timezone.now())
        _tell_owners_freed(b, f'{party.first_name} took a room at another PG')
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
    from ..agreements.document import build_document
    with system():  # reads the owner's template and both names
        build_document(Agreement.objects.select_related('booking__bed__room__property', 'booking__guest').get(pk=ag.pk))
    PoliceVerification.objects.create(organisation=b.organisation, booking=b, tenant=party, jurisdiction=prop.city)
    audit(b.organisation, party, 'booking.hold', b, after={'bed': bed.id, 'rent_paise': rent})
    return b


def _tell_owners_freed(b: Booking, why: str) -> None:
    with system():
        owners = owners_of(b.organisation)
        room = b.bed.room
    for o in owners:
        notify(o, 'booking.cancelled', f'{why}: Room {room.number}, bed {b.bed.label} is free again.',
               org=b.organisation, booking=str(b.id))


def cancel(b: Booking, actor: Party) -> Booking:
    """Cancel before move-in. A paid deposit is reversed with contra-entries, never deleted. The row is locked first
    so a deposit landing at the same moment either confirms before this (and is refunded here) or arrives after
    (and is refunded by the payment side)."""
    b = Booking.objects.select_for_update(of=('self',)).select_related('bed__room__property', 'guest').get(pk=b.pk)
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
    _tell_owners_freed(b, f'{b.guest.first_name} cancelled')
    return b


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
