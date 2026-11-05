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
