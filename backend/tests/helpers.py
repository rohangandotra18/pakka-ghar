from datetime import date

from apps.core.api_support import add_months, ist
from apps.core.rls import system
from apps.property.models import Bed


def bed(prop, room, label) -> Bed:
    with system():
        return Bed.objects.select_related('room__property').get(room__property=prop, room__number=room, label=label)


def period(start: date, months: int = 11):
    return (ist(start), ist(add_months(start, months)))
