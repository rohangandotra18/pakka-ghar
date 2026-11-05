"""Request IDs and one log line per request: method, path, status, time and who (never the body or the token)."""
import logging
import secrets
import time

log = logging.getLogger('pakka.requests')


class RequestLog:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get('X-Request-Id', '')[:64] or secrets.token_hex(8)
        request.request_id = rid
        start = time.monotonic()
        response = self.get_response(request)
        ms = int((time.monotonic() - start) * 1000)
        party = getattr(request, 'party', None)
        log.info('%s %s %s %dms party=%s rid=%s', request.method, request.path, response.status_code, ms,
                 party.id if party else '-', rid)
        response['X-Request-Id'] = rid
        return response


def client_ip(request) -> str:
    """The caller's address. Behind a proxy, set NUM_PROXIES so only the proxy's X-Forwarded-For entry is trusted."""
    from django.conf import settings
    n = getattr(settings, 'NUM_PROXIES', 0)
    fwd = [p.strip() for p in request.headers.get('X-Forwarded-For', '').split(',') if p.strip()]
    if n and len(fwd) >= n:
        return fwd[-n]
    return request.META.get('REMOTE_ADDR', '')


class Cors:
    """Lets the website (another origin) call the API. Bearer tokens only, no cookies, so no credentials mode.
    Allowed origins come from CORS_ORIGINS; with DEBUG, this machine and the local network are allowed too."""
    ALLOW_HEADERS = 'Authorization, Content-Type, Idempotency-Key, X-Org, X-Request-Id, Last-Event-ID'

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def allowed(origin: str) -> bool:
        import re

        from django.conf import settings
        if origin in settings.CORS_ORIGINS:
            return True
        return settings.DEBUG and bool(re.fullmatch(r'https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?', origin))

    def __call__(self, request):
        from django.http import HttpResponse
        origin = request.headers.get('Origin', '')
        ok = bool(origin) and self.allowed(origin)
        if request.method == 'OPTIONS' and ok and request.headers.get('Access-Control-Request-Method'):
            response = HttpResponse(status=204)
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = self.ALLOW_HEADERS
            response['Access-Control-Max-Age'] = '600'
        else:
            response = self.get_response(request)
        if ok:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Expose-Headers'] = 'X-Request-Id, Idempotent-Replay'
            response['Vary'] = 'Origin'
        return response
