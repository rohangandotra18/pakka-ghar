"""Background jobs (PDFs, WhatsApp reminders, KYC callbacks, hold expiry). Runs inline when REDIS_URL is unset."""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
app = Celery('pakka')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(['apps.core', 'apps.booking', 'apps.payments'])
