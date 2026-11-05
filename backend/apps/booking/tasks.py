from celery import shared_task
from django.db import transaction


@shared_task
def release_expired_holds() -> int:
    from .services import expire_holds
    with transaction.atomic():
        return expire_holds()
