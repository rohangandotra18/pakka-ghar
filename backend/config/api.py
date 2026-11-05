"""The one HTTP API. Its OpenAPI 3.1 schema (GET /api/openapi.json, exported to contracts/) is the contract the
app's TypeScript client is generated from."""
import json
import time

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import Max
from django.http import StreamingHttpResponse
from ninja import NinjaAPI, Router, Schema, Status

from apps.booking.api import router as tenant_router
from apps.booking.owner_api import router as owner_router
from apps.core.api_support import ApiError, bearer, party_of
from apps.core.models import Notification
from apps.core.staff_api import router as staff_router
from apps.core.rls import set_context
from apps.identity.api import router as identity_router
from apps.identity.privacy import router as privacy_router
from apps.maintenance.api import router as requests_router
from apps.payments.api import router as webhook_router
from apps.property.api import owner as property_owner_router
from apps.property.api import router as listings_router

api = NinjaAPI(title='Pakka Ghar API', version='1.0.0', auth=bearer, urls_namespace='api',
               description='Rentals and PGs in the Chandigarh Tricity. Money is integer paise. No cash, ever.')


class ErrorOut(Schema):
    code: str
    message: str


@api.exception_handler(ApiError)
def on_api_error(request, exc: ApiError):
    if not exc.commit:
        transaction.set_rollback(True)
    return api.create_response(request, {'code': exc.code, 'message': exc.message}, status=exc.status)


@api.exception_handler(IntegrityError)
def on_integrity(request, exc):
    transaction.set_rollback(True)
    return api.create_response(request, {'code': 'conflict', 'message': 'That clashes with something already saved. Refresh and try again.'}, status=409)


for r in (identity_router, listings_router, tenant_router, requests_router, owner_router, property_owner_router, webhook_router, staff_router, privacy_router):
    api.add_router('', r)


# ---- notifications and live events -------------------------------------------------------------------------

events = Router(tags=['events'])


class NotificationOut(Schema):
    id: int
    kind: str
    title: str
    data: dict
    created_at: str


def note_out(n: Notification) -> dict:
    return {'id': n.id, 'kind': n.kind, 'title': n.title, 'data': n.data, 'created_at': n.created_at.isoformat()}


@events.get('/notifications', response=list[NotificationOut])
def notifications(request, after: int = 0):
    return [note_out(n) for n in Notification.objects.filter(party=party_of(request), id__gt=after).order_by('-id')[:30]]


@events.get('/events', summary='Server-sent events: one per notification, as it happens')
def stream(request, after: int = 0):
    party_id = party_of(request).id
    last = int(request.headers.get('Last-Event-ID') or after or 0) or (
        Notification.objects.filter(party_id=party_id).aggregate(m=Max('id'))['m'] or 0)

    def gen():
        nonlocal last
        yield 'retry: 3000\n\n'
        deadline, quiet = time.monotonic() + 300, 0
        try:
            while time.monotonic() < deadline:
                with transaction.atomic():
                    set_context(None, party_id)
                    rows = list(Notification.objects.filter(party_id=party_id, id__gt=last).order_by('id')[:50])
                for n in rows:
                    last = n.id
                    yield f'id: {n.id}\nevent: {n.kind}\ndata: {json.dumps(note_out(n))}\n\n'
                quiet = 0 if rows else quiet + 1
                if quiet >= 7:
                    quiet = 0
                    yield ': ping\n\n'
                time.sleep(2)
        finally:
            connection.close()

    resp = StreamingHttpResponse(gen(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


api.add_router('', events)


class HealthOut(Schema):
    status: str
    database: bool
    version: str


@api.get('/health', response={200: HealthOut, 503: HealthOut}, auth=None, tags=['ops'], summary='For load balancers and uptime checks')
def health(request):
    try:
        with connection.cursor() as c:
            c.execute('SELECT 1')
            ok = c.fetchone()[0] == 1
    except Exception:  # noqa: BLE001 - any database failure means unhealthy
        ok = False
    body = {'status': 'ok' if ok else 'degraded', 'database': ok, 'version': api.version}
    return Status(200 if ok else 503, body)

if settings.DEBUG:
    from apps.core.dev_api import router as dev_router
    api.add_router('/dev', dev_router)
