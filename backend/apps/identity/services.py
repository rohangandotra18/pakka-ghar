"""OTP sign-in and DigiLocker identity checks. Providers are swappable; 'console' and 'fake' need no network."""
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.api_support import ApiError, sha256
from apps.core.models import Party

from .models import OtpChallenge, SessionToken

log = logging.getLogger('pakka')


def normalise_phone(raw: str) -> str:
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    if len(digits) != 10 or digits[0] not in '6789':
        raise ApiError(422, 'bad_phone', 'Enter a 10-digit Indian mobile number.')
    return '+91' + digits


def start_otp(raw_phone: str, ip: str | None = None) -> tuple[OtpChallenge, str]:
    phone = normalise_phone(raw_phone)
    since = timezone.now() - timedelta(minutes=10)
    if OtpChallenge.objects.filter(phone=phone, created_at__gte=since).count() >= settings.OTP_PER_PHONE_10MIN:
        raise ApiError(429, 'too_many_codes', 'Too many codes asked for. Try again in 10 minutes.')
    # one network asking for codes to many numbers is how SMS bills get run up
    if ip and OtpChallenge.objects.filter(ip=ip, created_at__gte=since).count() >= settings.OTP_PER_IP_10MIN:
        raise ApiError(429, 'too_many_codes', 'Too many codes asked for from this network. Try again in 10 minutes.')
    code = f'{secrets.randbelow(10**6):06d}'
    ch = OtpChallenge.objects.create(phone=phone, ip=ip or None, code_hash=sha256(f'{phone}:{code}'),
                                     expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS))
    if settings.OTP_PROVIDER == 'console':
        log.info('OTP for %s: %s', phone, code)
    else:  # pragma: no cover - wire the SMS/WhatsApp provider here
        raise ApiError(503, 'otp_unavailable', f'OTP provider {settings.OTP_PROVIDER} is not configured.')
    return ch, code


def verify_otp(challenge_id, code: str, device: str = '') -> tuple[Party, str, bool]:
    ch = OtpChallenge.objects.select_for_update().filter(pk=challenge_id).first()
    if not ch or ch.consumed_at or ch.expires_at < timezone.now():
        raise ApiError(400, 'code_expired', 'That code has expired. Ask for a new one.')
    if ch.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise ApiError(429, 'too_many_attempts', 'Too many wrong codes. Ask for a new one.')
    if not secrets.compare_digest(ch.code_hash, sha256(f'{ch.phone}:{code.strip()}')):
        OtpChallenge.objects.filter(pk=ch.pk).update(attempts=ch.attempts + 1)
        raise ApiError(400, 'wrong_code', 'That code is not right.', commit=True)
    ch.consumed_at = timezone.now()
    ch.save(update_fields=['consumed_at'])
    party, created = Party.objects.get_or_create(phone=ch.phone)
    token = secrets.token_urlsafe(32)
    SessionToken.objects.create(party=party, token_hash=sha256(token), device=device[:80])
    return party, token, created


# ---- DigiLocker ----------------------------------------------------------------------------------------

def mask_aadhaar(last4: str) -> str:
    if not re.fullmatch(r'\d{4}', last4 or ''):
        raise ValueError('need exactly the last four digits')
    return 'XXXXXXXX' + last4


def kyc_start(party: Party) -> dict:
    """Begin a DigiLocker consent flow. Returns where to send the person and the transaction to finish with."""
    txn = 'DL-' + secrets.token_hex(8)
    if settings.KYC_PROVIDER == 'fake':
        return {'txn': txn, 'redirect_url': f'https://digilocker.example/consent?txn={txn}'}
    raise ApiError(503, 'kyc_unavailable', 'DigiLocker is not configured.')  # pragma: no cover


def kyc_complete(party: Party, txn: str, auth_code: str) -> Party:
    """Finish the consent flow. A real client exchanges auth_code for the signed eAadhaar, checks the
    signature and keeps only the last four digits; nothing else about the ID is stored."""
    if settings.KYC_PROVIDER != 'fake':  # pragma: no cover
        raise ApiError(503, 'kyc_unavailable', 'DigiLocker is not configured.')
    if not txn.startswith('DL-') or not auth_code:
        raise ApiError(400, 'kyc_failed', 'DigiLocker did not confirm. Try again.')
    last4 = f'{int(sha256(party.phone)[:6], 16) % 10000:04d}'
    now = timezone.now()
    party.aadhaar_masked, party.digilocker_ref = mask_aadhaar(last4), txn
    party.kyc_verified_at = party.selfie_matched_at = now
    party.save(update_fields=['aadhaar_masked', 'digilocker_ref', 'kyc_verified_at', 'selfie_matched_at'])
    return party
