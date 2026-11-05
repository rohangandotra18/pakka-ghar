"""Daily housekeeping. Nothing here touches money, bookings or the audit trail."""
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone


@shared_task
def purge_expired() -> dict:
    """Sign-in codes older than a day and idempotency replays older than a week are no longer needed."""
    from apps.identity.models import OtpChallenge

    from .models import IdempotencyRecord
    from .rls import system
    now = timezone.now()
    with transaction.atomic(), system():
        codes, _ = OtpChallenge.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
        replays, _ = IdempotencyRecord.objects.filter(created_at__lt=now - timedelta(days=7)).delete()
    return {'codes': codes, 'replays': replays}
