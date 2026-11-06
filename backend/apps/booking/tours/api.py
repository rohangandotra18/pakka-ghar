"""Tenant API for tours: free times, book, list, cancel."""
from datetime import datetime
from uuid import UUID

from ninja import Router, Schema

from apps.core.api_support import OPTIONAL, ApiError, party_of

from .. import common
from . import services as svc

router = Router(tags=['tenant'])


# ---- tours ------------------------------------------------------------------------------------------------

class SlotsOut(Schema):
    slots: list[datetime]
    hours: dict


@router.get('/listings/{slug}/tour-slots', response=SlotsOut, auth=OPTIONAL, tags=['listings'], summary='Free tour times this week')
def tour_slots(request, slug: str):
    p = common.listing_by_slug(slug)
    return {'slots': svc.tour_slots(p) if p.status == 'published' else [], 'hours': svc.tour_hours(p)}


class TourIn(Schema):
    listing: str
    slot: datetime | None = None
    note: str = ''


class MyVisitOut(Schema):
    id: UUID
    listing: str
    name: str
    slot: datetime
    status: str
    note: str


def visit_out(v) -> dict:
    return {'id': v.id, 'listing': v.property.slug, 'name': v.property.name, 'slot': v.slot, 'status': v.status, 'note': v.note}


@router.get('/visits/mine', response=list[MyVisitOut], summary='Your tours, newest first')
def my_visits(request):
    from ..models import Visit
    qs = Visit.objects.filter(tenant=party_of(request)).select_related('property').order_by('-created_at')
    return [visit_out(v) for v in qs]


@router.post('/visits/{visit_id}/cancel', response=MyVisitOut, summary='Cancel a tour you asked for')
def cancel_visit(request, visit_id: UUID):
    from apps.core.api_support import notify

    from ..models import Visit
    v = Visit.objects.filter(pk=visit_id, tenant=party_of(request)).select_related('property').first()
    if not v:
        raise ApiError(404, 'not_found', 'No such tour.')
    if v.status in ('requested', 'confirmed'):
        v.status = 'cancelled'
        v.save(update_fields=['status', 'updated_at'])
        for o in common.owners_of(v.organisation):
            notify(o, 'visit.cancelled', f'{request.party.first_name} cancelled their tour.', org=v.organisation)
    return visit_out(v)


@router.post('/visits', response=MyVisitOut, summary='Book a tour at one of the free times')
def visit(request, body: TourIn):
    party = party_of(request)
    v = svc.request_visit(party, common.listing_by_slug(body.listing, taking_new=True), body.slot, body.note)
    return visit_out(v)
