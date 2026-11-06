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
    acc = accept(world['api'](owner), r.json()['id'])
    assert acc.status_code == 200, acc.content
    return api


def accept(owner_api, app_id, room=''):
    """The owner accepts with the code that signs their side of the agreement."""
    st = owner_api.post(f'/owner/applications/{app_id}/accept/start')
    if st.status_code != 200:
        return st
    st = st.json()
    return owner_api.post(f'/owner/applications/{app_id}/accept', {'room': room, 'challenge_id': st['challenge_id'], 'code': st['dev_code']})


def sign(api, booking_id):
    """The resident reads every page and signs with a code (before paying the deposit)."""
    pages = api.get(f'/agreements/{booking_id}').json()['pages']
    st = api.post(f'/agreements/{booking_id}/sign/start', {'pages_read': pages}).json()
    return api.post(f'/agreements/{booking_id}/sign', {'challenge_id': st['challenge_id'], 'code': st['dev_code'], 'pages_read': pages})
