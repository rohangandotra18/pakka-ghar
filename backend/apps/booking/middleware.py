"""Holds are released every minute by Celery beat when Redis runs. Without it (or if beat stops), a lapsed hold
would keep showing its bed as taken until someone booked. So API traffic also releases them, at most every
RELEASE_EVERY seconds per process, before the request runs: free beds are right however the server is deployed."""
import logging
import time

log = logging.getLogger('pakka')
RELEASE_EVERY = 30.0
DEPOSITS_EVERY = 3600.0   # overdue deposits: hourly is plenty


class ReleaseLapsedHolds:
    last = 0.0   # per process
    last_deposits = 0.0

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        now = time.monotonic()
        if request.path.startswith('/api/') and now - ReleaseLapsedHolds.last >= RELEASE_EVERY:
            ReleaseLapsedHolds.last = now
            try:
                from .bookings.services import expire_holds
                expire_holds()
            except Exception:   # never fail someone's request over housekeeping
                log.exception('releasing lapsed holds failed')
        if request.path.startswith('/api/') and now - ReleaseLapsedHolds.last_deposits >= DEPOSITS_EVERY:
            ReleaseLapsedHolds.last_deposits = now
            try:
                from django.db import transaction

                from .stay.services import settle_overdue_deposits
                with transaction.atomic():
                    settle_overdue_deposits()
            except Exception:
                log.exception('settling overdue deposits failed')
        return self.get_response(request)
