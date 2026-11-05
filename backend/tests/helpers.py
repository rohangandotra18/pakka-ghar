from datetime import date

from apps.core.api_support import add_months, ist
from apps.core.rls import system
from apps.property.models import Bed


def bed(prop, room, label) -> Bed:
    with system():
        return Bed.objects.select_related('room__property').get(room__property=prop, room__number=room, label=label)


def period(start: date, months: int = 11):
    return (ist(start), ist(add_months(start, months)))


def accepted(world, tenant, owner, listing='sidhu', **apply):
    """Apply as `tenant`, accept as `owner`; returns the tenant's API client."""
    api = world['api'](tenant)
    r = api.post('/applications', {'listing': listing, **apply})
    assert r.status_code == 200, r.content
    acc = world['api'](owner).post(f"/owner/applications/{r.json()['id']}/accept", {})
    assert acc.status_code == 200, acc.content
    return api
