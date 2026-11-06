"""The one HTTP API. Its OpenAPI 3.1 schema (GET /api/openapi.json, exported to contracts/) is the contract the
app's TypeScript client is generated from."""
import json
import time

from django.conf import settings
from django.db import DataError, IntegrityError, connection, transaction
from django.db.models import Max
from django.http import StreamingHttpResponse
from ninja import NinjaAPI, Router, Schema, Status

from apps.booking.agreements import api as agreements
from apps.booking.applications import api as applications
from apps.booking.applications import owner_api as applications_owner
from apps.booking.bookings import api as bookings
from apps.booking.owner_dashboard import beds, money, residents, today
from apps.booking.stay import api as stay
from apps.booking.tours import api as tours
from apps.booking.tours import owner_api as tours_owner
from apps.core.api_support import ApiError, bearer, party_of
from apps.core.models import Notification
from apps.core.rls import set_context
from apps.core.staff_api import router as staff_router
from apps.identity.api import router as identity_router
from apps.identity.privacy import router as privacy_router
from apps.maintenance.api import router as requests_router
from apps.payments.api import router as webhook_router
from apps.property.api import owner as property_owner_router
from apps.property.api import router as listings_router
from apps.property.photos import router as photos_router

class PakkaGharAPI(NinjaAPI):
    """Operation ids are the view's name, not its module path, so moving code between files never changes the
    contract. Two views with the same name would collide, so that is refused when the schema is built."""
    _ids: dict = {}

    def get_operation_id(self, operation) -> str:
        name = operation.view_func.__name__
        seen = self._ids.setdefault(name, operation.view_func)
        if seen is not operation.view_func:
            raise RuntimeError(f'Two API views are both named {name!r} ({seen.__module__} and {operation.view_func.__module__}); rename one.')
        return name


api = PakkaGharAPI(title='Pakka Ghar API', version='1.0.0', auth=bearer, urls_namespace='api',
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


@api.exception_handler(DataError)
def on_data_error(request, exc):
    """A value too long for its column (or out of range) is the caller's mistake, not a server error."""
    transaction.set_rollback(True)
    return api.create_response(request, {'code': 'too_long', 'message': 'One of the details is too long. Shorten it and try again.'}, status=422)


# one router per feature; each lives with its feature's code
FEATURES = (
    identity_router, listings_router,
    tours, applications, bookings, stay, requests_router,                         # tenant side
    today, tours_owner, beds, applications_owner, residents, money, property_owner_router,   # owner side
    webhook_router, staff_router, privacy_router, photos_router, agreements,
)
for r in FEATURES:
    api.add_router('', getattr(r, 'router', r))


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
