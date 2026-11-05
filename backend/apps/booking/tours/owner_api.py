"""Owner API for tours: confirm or decline a request, set tour hours."""
from uuid import UUID

from ninja import Router, Schema

from apps.booking.owner_dashboard.today import TodayOut, today_view
from apps.core.api_support import IST, ApiError

from .. import common
from ..models import Visit
from . import services as svc

router = Router(tags=['owner'])


@router.post('/owner/visits/{visit_id}/confirm', response=TodayOut)
def confirm_visit(request, visit_id: UUID):
    p = common.owner_property(request)
    v = Visit.objects.filter(pk=visit_id, property=p).first()
    if not v:
        raise ApiError(404, 'not_found', 'No such visit.')
    v.status = 'confirmed'
    v.save(update_fields=['status', 'updated_at'])
    from apps.core.api_support import notify
    notify(v.tenant, 'visit.confirmed', f'{p.name} confirmed your visit on {v.slot.astimezone(IST):%A at %-I %p}.'.replace('AM', 'am').replace('PM', 'pm'), org=p.organisation)
    return today_view(request)


@router.post('/owner/visits/{visit_id}/decline', response=TodayOut, summary='Turn down a visit; the tenant is told')
def decline_visit(request, visit_id: UUID):
    p = common.owner_property(request)
    v = Visit.objects.filter(pk=visit_id, property=p, status='requested').first()
    if not v:
        raise ApiError(404, 'not_found', 'No such visit request.')
    v.status = 'cancelled'
    v.save(update_fields=['status', 'updated_at'])
    from apps.core.api_support import notify
    notify(v.tenant, 'visit.declined', f'{p.name} can’t do that visit. Ask for another time in the app.', org=p.organisation)
    return today_view(request)


class TourHoursIn(Schema):
    days: list[int]       # 0 = Monday
    start: str            # "10:00"
    end: str              # "18:00"
    minutes: int = 30


@router.put('/owner/tour-hours', response=dict, summary='When tenants can book tours')
def tour_hours(request, body: TourHoursIn):
    import re
    p = common.owner_property(request)
    ok = (all(0 <= d <= 6 for d in body.days) and re.fullmatch(r'\d\d:\d\d', body.start) and re.fullmatch(r'\d\d:\d\d', body.end)
          and body.start < body.end and body.minutes in (15, 30, 45, 60))
    if not ok:
        raise ApiError(422, 'bad_hours', 'Pick days, a start before the end (HH:MM), and 15–60 minute tours.')
    p.attributes = {**(p.attributes or {}), 'tour_hours': body.model_dump()}
    p.save(update_fields=['attributes', 'updated_at'])
    return svc.tour_hours(p)
