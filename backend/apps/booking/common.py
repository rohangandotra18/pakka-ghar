"""Lookups several booking features share: the owners of an organisation, a listing by slug, the owner's PG."""
from django.utils import timezone

from apps.core.api_support import ApiError, owner_org
from apps.core.models import Membership, Party
from apps.property.models import Property

from .models import Booking


def owners_of(org) -> list[Party]:
    return [m.party for m in Membership.objects.filter(organisation=org, role__in=['owner', 'manager']).select_related('party')]


def listing_by_slug(slug: str, taking_new: bool = False) -> Property:
    """A listed PG by its slug, or 404. With taking_new, only a live PG: a paused one (after a confirmed cash report)
    takes no new applications, bids or tours, though bookings already under way can finish."""
    p = Property.objects.filter(slug=slug).exclude(status='draft').first()
    if not p:
        raise ApiError(404, 'not_found', 'No such PG.')
    if taking_new and p.status != 'published':
        raise ApiError(409, 'paused', f'{p.name} isn’t taking new tenants right now.')
    return p


def owner_property(request) -> Property:
    """The signed-in owner's PG (their first), with any stays that started today made active."""
    org = owner_org(request)
    p = Property.objects.filter(organisation=org).order_by('created_at').first()
    if not p:
        raise ApiError(404, 'no_property', 'Add your property first.')
    from .bookings.services import activate_started
    activate_started()
    return p


def current_residents(p: Property):
    """Everyone living at the PG now, by room and bed."""
    now = timezone.now()
    return (Booking.objects.filter(bed__room__property=p, status='active', stay_period__contains=now)
            .select_related('guest', 'bed__room', 'police').order_by('bed__room__number', 'bed__label'))
