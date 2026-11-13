"""What every endpoint shares: sign-in, the row-level-security context, idempotency, errors and helpers."""
import functools
import hashlib
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from ninja.security import HttpBearer

from .models import AuditEvent, IdempotencyRecord, Membership, Notification, Organisation, Party
from .rls import set_context

IST = ZoneInfo('Asia/Kolkata')


class ApiError(Exception):
    """An error the caller can act on. The request's writes are rolled back unless `commit` is set
    (e.g. a wrong OTP still counts as an attempt)."""
    def __init__(self, status: int, code: str, message: str, commit: bool = False):
        super().__init__(message)
        self.status, self.code, self.message, self.commit = status, code, message, commit


def sha256(s: str | bytes) -> str:
    return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()


# ---- sign-in -----------------------------------------------------------------------------------------

def _org_for(request: HttpRequest, party: Party) -> Organisation | None:
    """The organisation a request acts for: the X-Org header if the caller belongs to it, else their first."""
    ms = Membership.objects.filter(party=party).select_related('organisation').order_by('created_at')
    wanted = request.headers.get('X-Org')
    for m in ms:
        if not wanted or str(m.organisation_id) == wanted:
            return m.organisation
    if wanted:
        raise ApiError(403, 'not_a_member', 'You are not a member of that organisation.')
    return None


class TokenAuth(HttpBearer):
    def authenticate(self, request, token):
        from apps.identity.models import SessionToken
        st = SessionToken.objects.select_related('party').filter(token_hash=sha256(token), revoked_at__isnull=True).first()
        if not st:
            return None
        if timezone.now() - (st.last_used_at or st.created_at) > timedelta(days=settings.SESSION_IDLE_DAYS):
            SessionToken.objects.filter(pk=st.pk).update(revoked_at=timezone.now())
            return None
        if not st.last_used_at or timezone.now() - st.last_used_at > timedelta(minutes=5):
            SessionToken.objects.filter(pk=st.pk).update(last_used_at=timezone.now())
        request.party = st.party
        request.session_token = st
        request.org = _org_for(request, st.party)
        set_context(request.org.id if request.org else None, st.party.id)
        return st.party


class Anonymous:
    """Someone browsing without an account. Public endpoints accept them."""
    def __bool__(self):
        return True


def anonymous(request):
    request.party, request.org = None, None
    set_context(None, None)
    return Anonymous()


bearer = TokenAuth()
OPTIONAL = [bearer, anonymous]


def party_of(request) -> Party:
    if not getattr(request, 'party', None):
        raise ApiError(401, 'sign_in', 'Sign in first.')
    return request.party


def owner_org(request) -> Organisation:
    party_of(request)
    if not request.org:
        raise ApiError(403, 'not_an_owner', 'This needs an owner account.')
    return request.org


def require_verified(party: Party) -> None:
    if not party.verified:
        raise ApiError(403, 'verify_identity', 'Verify your identity with DigiLocker first.')


# ---- idempotency ---------------------------------------------------------------------------------------

def idempotent(view):
    """POSTs that hold a bed or move money take an Idempotency-Key header. The same key with the same request
    replays the first response; the same key with a different request is refused with 409."""
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        key = request.headers.get('Idempotency-Key', '').strip()
        if not key:
            raise ApiError(400, 'idempotency_key_required', 'Send an Idempotency-Key header.')
        party = party_of(request)
        fp = sha256(f'{request.method} {request.path}\n'.encode() + (request.body or b''))
        # A double tap or a retry can bring the same key twice at once. Both would find no record and both run the
        # view; the second then fails on the unique key. Holding a lock on (person, key) until this request's
        # transaction ends makes the second wait, find the first's record and replay it.
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', [f'idem:{party.id}:{key}'])
        rec = IdempotencyRecord.objects.filter(party=party, key=key).first()
        if rec:
            if rec.fingerprint != fp:
                raise ApiError(409, 'idempotency_key_reused', 'That Idempotency-Key was used for a different request.')
            return JsonResponse(rec.body, status=rec.status, headers={'Idempotent-Replay': 'true'})
        request.idempotency = (key, fp)
        body = view(request, *args, **kwargs)
        data = json.loads(json.dumps(body, default=_json_default))
        IdempotencyRecord.objects.create(party=party, organisation=getattr(request, 'org', None), key=key, fingerprint=fp, status=200, body=data)
        return body
    return wrapper


def _json_default(o):
    if hasattr(o, 'model_dump'):
        return o.model_dump(mode='json')
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


# ---- audit and notifications -----------------------------------------------------------------------------

def audit(org, actor, action: str, obj, before: dict | None = None, after: dict | None = None) -> None:
    AuditEvent.objects.create(organisation=org, actor=actor, action=action, entity=type(obj).__name__,
                              entity_id=str(obj.pk), before=before or {}, after=after or {})


def notify(party: Party, kind: str, title: str, org=None, **data) -> None:
    """Tell someone in the app. Written with the system role: only the recipient can read their notifications,
    so the caller (usually someone else) could not insert it otherwise."""
    from .rls import system
    with system():
        Notification.objects.create(party=party, organisation=org, kind=kind, title=title, data=data)


# ---- dates ---------------------------------------------------------------------------------------------

def today() -> date:
    return timezone.now().astimezone(IST).date()


def ist(d: date, hh: int = 0, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=IST)


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1) if d.day == 1 else date(d.year + y, m + 1, min(d.day, 28))


def fy_label(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f'{start}-{str(start + 1)[2:]}'


def month_label(d: date) -> str:
    return d.strftime('%b %Y')


def next_friday_6pm(now: datetime | None = None) -> datetime:
    n = (now or timezone.now()).astimezone(IST)
    days = (4 - n.weekday()) % 7
    cand = ist(n.date() + timedelta(days=days), 18)
    return cand if cand > n else cand + timedelta(days=7)
