from celery import shared_task
from django.db import transaction


@shared_task
def release_expired_holds() -> int:
    from .bookings.services import expire_holds
    with transaction.atomic():
        return expire_holds()


@shared_task
def settle_overdue_deposits() -> int:
    from .stay.services import settle_overdue_deposits as run
    with transaction.atomic():
        return run()


@shared_task
def announce_ended_bidding() -> int:
    from apps.core.rls import system

    from .applications.services import announce_ended_bidding as run
    with transaction.atomic(), system():
        return run()
