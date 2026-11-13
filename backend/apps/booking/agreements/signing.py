"""Signing: every page read and a one-time code; signatures are append-only. The owner signs when accepting a
request, the resident before paying the deposit."""
import re
import secrets

from django.conf import settings
from django.utils import timezone

from apps.booking.agreements.document import seal
from apps.booking.common import owners_of
from apps.core.api_support import ApiError, audit, notify
from apps.core.models import Party
from apps.core.rls import system

from ..models import Agreement, Signature

# ---- signing ----------------------------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip().lower()


def _check_can_sign(a: Agreement, role: str, pages_read: int) -> None:
    """Checked when the code is sent and again when it is used: the booking can be cancelled in between.
    The owner signs when accepting; the resident signs before paying the deposit, so money moves only once
    both have agreed."""
    b = a.booking
    b.refresh_from_db(fields=['status'])
    if not a.document:
        raise ApiError(409, 'no_document', 'The agreement isn’t ready yet.')
    if pages_read < a.pages:
        raise ApiError(409, 'read_all', f'Read all {a.pages} pages before signing.')
    if b.status not in ('hold', 'confirmed', 'active'):
        raise ApiError(409, 'not_booked', 'This booking is no longer going ahead.')
    if a.signatures.filter(role=role).exists():
        raise ApiError(409, 'already_signed', 'Already signed.')


def start_signing(a: Agreement, party: Party, role: str, pages_read: int) -> tuple:
    from apps.identity.services import start_otp
    _check_can_sign(a, role, pages_read)
    with system():
        ch, code = start_otp(party.phone)
    return ch, code


def use_code(party: Party, challenge_id, code: str):
    """Check and consume a one-time code sent to this person's phone."""
    from apps.identity.models import OtpChallenge
    from apps.identity.services import otp_hash
    with system():
        ch = OtpChallenge.objects.select_for_update().filter(pk=challenge_id, phone=party.phone).first()
        if not ch or ch.consumed_at or ch.expires_at < timezone.now():
            raise ApiError(400, 'code_expired', 'That code has expired. Ask for a new one.')
        if ch.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise ApiError(429, 'too_many_attempts', 'Too many wrong codes. Ask for a new one.')
        if not secrets.compare_digest(ch.code_hash, otp_hash(ch.phone, code or '')):
            OtpChallenge.objects.filter(pk=ch.pk).update(attempts=ch.attempts + 1)
            raise ApiError(400, 'wrong_code', 'That code is not right.', commit=True)
        ch.consumed_at = timezone.now()
        ch.save(update_fields=['consumed_at'])
    return ch


def record_signature(a: Agreement, party: Party, role: str, ch, pages_read: int, ip: str | None, user_agent: str,
                     typed_name: str = '') -> Agreement:
    Signature.objects.create(organisation=a.organisation, agreement=a, party=party, role=role,
                             typed_name=(typed_name.strip() or party.name)[:120], document_sha256=a.document_sha256,
                             pages_read=pages_read, otp_challenge=ch.id, ip=ip or None, user_agent=(user_agent or '')[:200])
    now = timezone.now()
    b = a.booking
    if role == 'tenant':
        a.tenant_signed_at = now
        a.esign_ref = a.esign_ref or 'ESIGN-' + secrets.token_hex(5).upper()
        for o in owners_of(b.organisation):
            notify(o, 'agreement.sign', f'{party.first_name} signed the agreement. The booking completes when the deposit is paid.',
                   org=a.organisation, booking=str(b.id))
    else:
        a.owner_signed_at = now
    a.save(update_fields=['tenant_signed_at', 'owner_signed_at', 'esign_ref', 'updated_at'])
    audit(a.organisation, party, f'agreement.sign.{role}', a, after={'sha256': a.document_sha256})
    if a.tenant_signed_at and a.owner_signed_at:
        with system():
            seal(Agreement.objects.select_related('booking').get(pk=a.pk))
        a.refresh_from_db()
    return a


def confirm_signing(a: Agreement, party: Party, role: str, challenge_id, code: str, typed_name: str, pages_read: int,
                    ip: str | None, user_agent: str) -> Agreement:
    """The one-time code proves who is signing; a typed name, when given, must match the account."""
    if typed_name.strip() and _norm(typed_name) != _norm(party.name):
        raise ApiError(422, 'name_mismatch', f'Type your full name exactly as on your account: {party.name}.')
    _check_can_sign(a, role, pages_read)
    ch = use_code(party, challenge_id, code)
    return record_signature(a, party, role, ch, pages_read, ip, user_agent, typed_name)
