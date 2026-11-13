"""Living there and leaving: notice, move-out rating, deposit settlement, the owner's rating, stay labels."""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from apps.booking.common import owners_of
from apps.core.api_support import ApiError, audit, ist, month_label, notify, today
from apps.core.ledger import post
from apps.core.models import Party

from ..models import Booking, Rating

ASPECTS = ('Cleanliness', 'Food', 'Owner response', 'Value')


# ---- living there --------------------------------------------------------------------------------------

def give_notice(b: Booking, party: Party) -> Booking:
    if b.status != 'active':
        raise ApiError(409, 'not_living_here', 'You can give notice once you have moved in.')
    if b.notice_given_on:
        return b
    t = today()
    leave = t + timedelta(days=30 * b.bed.room.property.notice_months)
    if b.stay_period.upper:   # never past the agreement's own end (the bed may be booked from then)
        leave = min(leave, b.stay_period.upper.astimezone(ist(t).tzinfo).date())
    b.notice_given_on = t
    b.stay_period = DateTimeTZRange(b.stay_period.lower, ist(leave))
    b.save(update_fields=['notice_given_on', 'stay_period', 'updated_at'])
    audit(b.organisation, party, 'booking.notice', b, after={'leaves_on': leave.isoformat()})
    for o in owners_of(b.organisation):
        notify(o, 'booking.notice', f'{party.first_name} gave notice and leaves on {leave:%-d %B}.', org=b.organisation, booking=str(b.id))
    return b


def leaves_on(b: Booking) -> date | None:
    return b.stay_period.upper.astimezone(ist(today()).tzinfo).date() if b.notice_given_on and b.stay_period.upper else None


def notice_charge(b: Booking) -> tuple[int, date]:
    """Leaving before the notice period is served: the rent for the days still to run comes from the deposit (clause 4
    of the agreement). Days already covered by this month's paid rent aren't charged again. Returns (paise, the day
    the notice would have ended)."""
    from apps.core.api_support import month_start
    from apps.payments.models import Invoice
    t = today()
    if b.notice_given_on and leaves_on(b):
        ends = leaves_on(b)
    else:
        ends = t + timedelta(days=30 * b.bed.room.property.notice_months)
        if b.stay_period.upper:
            ends = min(ends, b.stay_period.upper.astimezone(ist(t).tzinfo).date())
    this_month = month_start(t)
    paid = Invoice.objects.filter(booking=b, period=this_month, status='paid').exists()
    covered_to = (this_month + timedelta(days=32)).replace(day=1) if paid else t
    days = max(0, (ends - max(t, covered_to)).days)
    return b.rent_paise * days // 30, ends


def end_and_rate(b: Booking, party: Party, aspects: dict[str, int], deposit_on_time: bool | None, comment: str) -> Booking:
    if b.status not in ('active', 'confirmed'):
        raise ApiError(409, 'no_stay', 'There is no stay to end.')
    if b.stay_period.lower > timezone.now():  # never moved in: that is a cancel, with the deposit back in full
        raise ApiError(409, 'not_moved_in', 'You haven’t moved in yet. Cancel the booking instead and the deposit comes back in full.')
    if set(aspects) != set(ASPECTS) or not all(1 <= int(v) <= 5 for v in aspects.values()):
        raise ApiError(422, 'rate_all', 'Rate all four, from 1 to 5 stars.')
    charge, _ = notice_charge(b)   # worked out before the stay's end date moves to today
    score = Decimal(sum(int(v) for v in aspects.values()) / len(aspects)).quantize(Decimal('0.1'))
    Rating.objects.create(organisation=b.organisation, booking=b, tenant=party, direction='tenant_to_pg',
                          aspects=aspects, score=score, comment=comment[:2000], deposit_on_time=deposit_on_time)
    now = timezone.now()
    b.status = 'ended'
    b.ended_on = today()
    b.stay_period = DateTimeTZRange(b.stay_period.lower, max(now, b.stay_period.lower + timedelta(seconds=1)))
    b.deposit_outcome = 'Deposit refund in progress'
    b.autopay = False
    b.attributes = {**(b.attributes or {}), 'notice_charge_paise': min(charge, b.deposit_paise)}
    b.save(update_fields=['status', 'ended_on', 'stay_period', 'deposit_outcome', 'autopay', 'attributes', 'updated_at'])
    audit(b.organisation, party, 'booking.end', b, after={'score': str(score)})
    for o in owners_of(b.organisation):
        owed = b.attributes.get('notice_charge_paise', 0)
        notify(o, 'booking.ended', f'{party.first_name} moved out{f" before their notice ended (₹{owed // 100:,} unserved notice from the deposit)" if owed else ""}. '
               'Settle the deposit within 7 days, or it is returned automatically.', org=b.organisation, booking=str(b.id))
    return b


def settle_deposit(b: Booking, actor: Party, deduction_paise: int = 0, reason: str = '') -> Booking:
    """Return the deposit from escrow, less any deduction the owner explains."""
    if b.status not in ('ended', 'cancelled'):
        raise ApiError(409, 'still_living_here', 'Settle the deposit after the resident moves out.')
    from apps.core.ledger import balance
    # Locked before the balance is read: the owner's button and the hourly automatic return can settle the same
    # deposit at once, and both reading it as still held would pay it out twice.
    list(Booking.objects.select_for_update(of=('self',)).filter(pk=b.pk).values_list('pk', flat=True))
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


DEPOSIT_DAYS = 7          # clause 3 of the agreement: the owner settles within 7 days of move-out
REMIND_ON = (3, 6)


def settle_overdue_deposits() -> int:
    """Owners have 7 days after move-out to settle a deposit; they're reminded on days 3 and 6. On day 7 an
    unsettled deposit goes back to the resident in full, less only any rent for unserved notice. Runs hourly
    (Celery beat, and from API traffic). Returns how many were returned."""
    from apps.core.ledger import balance
    from apps.core.rls import system
    returned = 0
    with system():
        due = list(Booking.objects.filter(status='ended', deposit_outcome='Deposit refund in progress', ended_on__isnull=False)
                   .select_related('guest', 'organisation', 'bed__room'))
        for b in due:
            days = (today() - b.ended_on).days
            held = -balance(b.organisation, 'deposit_liability', b.guest)
            if held <= 0:
                continue
            attrs = dict(b.attributes or {})
            if days >= DEPOSIT_DAYS:
                charge = min(int(attrs.get('notice_charge_paise', 0)), held)
                try:
                    with transaction.atomic():
                        settle_deposit(b, None, charge, 'rent for unserved notice' if charge else '')
                except ApiError:   # the owner settled it a moment ago: nothing left to return
                    continue
                for o in owners_of(b.organisation):
                    notify(o, 'deposit.auto', f'{b.guest.first_name}’s deposit wasn’t settled in {DEPOSIT_DAYS} days, so ₹{(held - charge) // 100:,} '
                           f'went back to them{f" (₹{charge // 100:,} unserved notice kept for you)" if charge else ""}.', org=b.organisation, booking=str(b.id))
                returned += 1
                continue
            sent = set(attrs.get('deposit_reminders', []))
            for d in REMIND_ON:
                if days >= d and d not in sent:
                    left = DEPOSIT_DAYS - days
                    for o in owners_of(b.organisation):
                        notify(o, 'deposit.reminder', f'Settle {b.guest.first_name}’s deposit: {left} day{"s" if left != 1 else ""} left, '
                               'then it’s returned in full automatically.', org=b.organisation, booking=str(b.id))
                    sent.add(d)
                    break   # one reminder at a time
            if sent != set(attrs.get('deposit_reminders', [])):
                Booking.objects.filter(pk=b.pk).update(attributes={**attrs, 'deposit_reminders': sorted(sent)})
    return returned
