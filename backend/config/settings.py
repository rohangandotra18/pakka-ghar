"""Pakka Ghar backend settings. Every value that differs between machines comes from the environment."""
import os
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = '') -> str:
    return os.environ.get(name, default)


DEBUG = env('DEBUG', '1') == '1'
SECRET_KEY = env('SECRET_KEY', 'dev-only-not-secret' if DEBUG else '')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY must be set when DEBUG is off')
ALLOWED_HOSTS = [h for h in env('ALLOWED_HOSTS', '*' if DEBUG else '').split(',') if h]

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.postgres',
    'apps.core',
    'apps.identity',
    'apps.property',
    'apps.booking',
    'apps.payments',
    'apps.maintenance',
]

MIDDLEWARE = [
    'apps.core.middleware.RequestLog',
    'apps.core.middleware.Cors',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
# The API authenticates with bearer tokens in a header and sets no cookies, so cross-site request forgery
# (which rides on cookies) doesn't apply; Django's CSRF middleware is deliberately not used.
SILENCED_SYSTEM_CHECKS = ['security.W003']

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# One PostgreSQL database of record. The web process connects as a role that is subject to row-level
# security; webhooks, scheduled jobs and seeding switch to DB_SYSTEM_ROLE (BYPASSRLS) explicitly.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', 'pakka'),
        'USER': env('DB_USER', 'pakka'),
        'PASSWORD': env('DB_PASSWORD', 'pakka'),
        'HOST': env('DB_HOST', 'localhost'),
        'PORT': env('DB_PORT', '5432'),
        'ATOMIC_REQUESTS': True,
        'CONN_MAX_AGE': 0,
    }
}
DB_SYSTEM_ROLE = env('DB_SYSTEM_ROLE', 'pakka_system')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
TIME_ZONE = 'Asia/Kolkata'
LANGUAGE_CODE = 'en-in'
USE_I18N = False

# Providers. 'fake' runs everything locally with no network; swap per service when the contracts are signed.
OTP_PROVIDER = env('OTP_PROVIDER', 'console')          # console | msg91
KYC_PROVIDER = env('KYC_PROVIDER', 'fake')             # fake | digilocker
PAYMENT_PROVIDER = env('PAYMENT_PROVIDER', 'fake')     # fake | razorpay
ESIGN_PROVIDER = env('ESIGN_PROVIDER', 'fake')         # fake | leegality
RAZORPAY_KEY_ID = env('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = env('RAZORPAY_KEY_SECRET')
RAZORPAY_WEBHOOK_SECRET = env('RAZORPAY_WEBHOOK_SECRET', 'dev-webhook-secret' if DEBUG else '')

# Demo conveniences (only with DEBUG): the OTP comes back in the response so the app can fill it in.
DEV_ECHO_OTP = DEBUG and env('DEV_ECHO_OTP', '1') == '1'

OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5
OTP_PER_PHONE_10MIN = 5
OTP_PER_IP_10MIN = int(env('OTP_PER_IP_10MIN', '20'))
CORS_ORIGINS = [o for o in env('CORS_ORIGINS', '').split(',') if o]   # the website's address in production
NUM_PROXIES = int(env('NUM_PROXIES', '0'))   # load balancers in front of the app, for the client's real address
# Photos: taken in the app's camera at the building, moments before upload (apps.property.photos)
MEDIA_ROOT = Path(env('MEDIA_ROOT', str(BASE_DIR / '.media')))
MEDIA_URL = env('MEDIA_URL', '/media/')
# Agreements and other private files: never served directly, only through an endpoint that checks who is asking
PRIVATE_ROOT = Path(env('PRIVATE_ROOT', str(BASE_DIR / '.private')))
AGREEMENT_MAX_BYTES = 10 * 1024 * 1024
AGREEMENT_MAX_PAGES = 30
PHOTO_MAX_BYTES = 12 * 1024 * 1024
PHOTO_MAX_AGE_S = 600          # taken in the last 10 minutes
PHOTO_MAX_DISTANCE_M = 150     # from the owner's pin
PHOTO_MAX_ACCURACY_M = 100     # the phone's GPS fix must be at least this good

HOLD_MINUTES = 10                 # a bed held while the tenant pays the deposit
OFFER_HOLD_HOURS = 24             # an accepted offer holds the bed this long
OFFER_CAP_BP = 1500               # offers can go at most 15% over the listed rent
RATING_REVEAL_DAYS = 14

# Background jobs: Redis + Celery when REDIS_URL is set, otherwise tasks run inline.
REDIS_URL = env('REDIS_URL')
CELERY_BROKER_URL = REDIS_URL or 'memory://'
CELERY_TASK_ALWAYS_EAGER = not REDIS_URL
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'release-expired-holds': {'task': 'apps.booking.tasks.release_expired_holds', 'schedule': 60.0},
    'charge-rent': {'task': 'apps.payments.tasks.charge_rent_for_month', 'schedule': crontab(minute=5, hour=0, day_of_month=1)},
    'settle-to-banks': {'task': 'apps.payments.tasks.settle_all', 'schedule': crontab(minute=0, hour=10)},
    'purge-expired': {'task': 'apps.core.tasks.purge_expired', 'schedule': crontab(minute=30, hour=3)},
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'pakka': {'handlers': ['console'], 'level': 'INFO'}},
}

# ---- production ------------------------------------------------------------------------------------------
# With DEBUG off: HTTPS only, strict headers, and the server refuses to start without the secrets it needs.
if not DEBUG:
    missing = [k for k in ('ALLOWED_HOSTS', 'DB_PASSWORD', 'RAZORPAY_WEBHOOK_SECRET') if not env(k)]
    if PAYMENT_PROVIDER == 'razorpay':
        missing += [k for k in ('RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET') if not env(k)]
    if missing:
        raise RuntimeError('Set these before running with DEBUG off: ' + ', '.join(missing))
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env('SECURE_SSL_REDIRECT', '1') == '1'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'no-referrer'
    X_FRAME_OPTIONS = 'DENY'
    DATABASES['default']['CONN_MAX_AGE'] = int(env('DB_CONN_MAX_AGE', '60'))
    DATABASES['default']['CONN_HEALTH_CHECKS'] = True
