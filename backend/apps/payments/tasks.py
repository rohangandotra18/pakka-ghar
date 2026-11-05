"""Scheduled money jobs. Each runs with the system role because it spans every owner."""
from celery import shared_task
from django.db import transaction


@shared_task
def charge_rent_for_month() -> int:
    from apps.booking.models import Booking
    from apps.core.api_support import today
    from apps.core.rls import system

    from .services import charge_month
    n = 0
    with transaction.atomic(), system():
        for b in Booking.objects.filter(status='active'):
            charge_month(b, today())
            n += 1
    return n


@shared_task
def settle_all() -> int:
    from apps.core.models import Organisation
    from apps.core.rls import system

    from .services import settle_to_bank
    with transaction.atomic(), system():
        return sum(settle_to_bank(o) for o in Organisation.objects.filter(kind='owner'))
