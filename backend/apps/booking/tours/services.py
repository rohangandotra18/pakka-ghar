"""Tours: free times from the owner's tour hours, one tour per slot."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.booking.common import owners_of
from apps.core.api_support import ApiError, ist, notify, today
from apps.core.models import Party
from apps.core.rls import system
from apps.property.models import Property

from ..models import Visit

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
    try:
        with transaction.atomic():
            v = Visit.objects.create(organisation=prop.organisation, property=prop, tenant=party, slot=slot, note=note.strip()[:200])
    except IntegrityError:   # someone took it a moment ago
        raise ApiError(409, 'slot_taken', 'That time was just taken. Pick another.') from None
    when = slot.astimezone(ist(today()).tzinfo).strftime('%a %-d %b, %-I:%M %p').replace('AM', 'am').replace('PM', 'pm')
    for o in owners_of(prop.organisation):
        notify(o, 'visit.new', f'{party.first_name} asked for a tour on {when}.', org=prop.organisation, visit=str(v.id))
    return v
