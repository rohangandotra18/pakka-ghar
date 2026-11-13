"""Scheduled money jobs. Each runs with the system role because it spans every owner."""
from celery import shared_task
from django.db import transaction


@shared_task
def charge_rent_for_month() -> int:
    """Runs on each of the first five mornings of the month; a booking already billed is left alone, so a run that
    failed or was missed is made up the next day. Each booking is billed on its own, so one that fails is logged
    and skipped instead of undoing everyone else's bill. Returns how many bookings have this month's invoice."""
    import logging

    from apps.booking.models import Booking
    from apps.core.api_support import today
    from apps.core.rls import system

    from .services import charge_month
    log = logging.getLogger('pakka')
    n = 0
    with transaction.atomic(), system():
        for b in Booking.objects.filter(status='active'):
            try:
                with transaction.atomic():   # a savepoint: this booking's bill stands or falls alone
                    charge_month(b, today())
                n += 1
            except Exception:
                log.exception('rent for booking %s could not be charged; tomorrow\'s run tries again', b.pk)
    return n


@shared_task
def settle_all() -> int:
    from apps.core.models import Organisation
    from apps.core.rls import system

    from .services import settle_to_bank
    with transaction.atomic(), system():
        return sum(settle_to_bank(o) for o in Organisation.objects.filter(kind='owner'))
