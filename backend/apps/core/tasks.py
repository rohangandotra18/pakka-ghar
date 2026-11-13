"""Daily housekeeping. Nothing here touches money, bookings or the audit trail."""
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

NOTIFICATION_KEEP_DAYS = 90


@shared_task
def purge_expired() -> dict:
    """Sign-in codes older than a day, idempotency replays older than a week, sign-ins that can no longer be used
    (signed out a month ago, or idle past SESSION_IDLE_DAYS), and notifications older than NOTIFICATION_KEEP_DAYS
    (they are delivered live; the app keeps no history of them) are no longer needed."""
    from django.conf import settings
    from django.db.models import Q
    from django.db.models.functions import Coalesce

    from apps.identity.models import OtpChallenge, SessionToken

    from .models import IdempotencyRecord, Notification
    from .rls import system
    now = timezone.now()
    with transaction.atomic(), system():
        codes, _ = OtpChallenge.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
        replays, _ = IdempotencyRecord.objects.filter(created_at__lt=now - timedelta(days=7)).delete()
        sessions, _ = (SessionToken.objects.annotate(seen=Coalesce('last_used_at', 'created_at'))
                       .filter(Q(revoked_at__lt=now - timedelta(days=30)) |
                               Q(seen__lt=now - timedelta(days=settings.SESSION_IDLE_DAYS))).delete())
        notes, _ = Notification.objects.filter(created_at__lt=now - timedelta(days=NOTIFICATION_KEEP_DAYS)).delete()
    return {'codes': codes, 'replays': replays, 'sessions': sessions, 'notifications': notes}
