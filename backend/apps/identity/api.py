"""Sign-in, the person's profile, and DigiLocker verification."""
from datetime import date
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from ninja import Router, Schema, Status

from apps.core.api_support import ApiError, bearer, party_of

from . import services

router = Router(tags=['identity'])


class OtpStartIn(Schema):
    phone: str


class OtpStartOut(Schema):
    challenge_id: UUID
    phone: str
    dev_code: str | None = None  # only when the server runs with DEBUG, so the demo can fill it in


@router.post('/auth/otp/start', response=OtpStartOut, auth=None, summary='Send a 6-digit code by SMS or WhatsApp')
def otp_start(request, body: OtpStartIn):
    from apps.core.middleware import client_ip
    ch, code = services.start_otp(body.phone, client_ip(request) or None)
    return {'challenge_id': ch.id, 'phone': ch.phone, 'dev_code': code if settings.DEV_ECHO_OTP else None}


class OtpVerifyIn(Schema):
    challenge_id: UUID
    code: str
    device: str = ''


class MembershipOut(Schema):
    organisation_id: UUID
    name: str
    role: str


class MeOut(Schema):
    id: UUID
    phone: str
    name: str
    works_at: str
    looking_for: str
    move_in_on: date | None
    verified: bool
    aadhaar_masked: str
    profile: dict
    memberships: list[MembershipOut]


class SessionOut(Schema):
    token: str
    new_account: bool
    me: MeOut


def me_out(p) -> dict:
    return {'id': p.id, 'phone': p.phone, 'name': p.name, 'works_at': p.works_at, 'looking_for': p.looking_for,
            'move_in_on': p.move_in_on, 'verified': p.verified, 'aadhaar_masked': p.aadhaar_masked, 'profile': p.profile or {},
            'memberships': [{'organisation_id': m.organisation_id, 'name': m.organisation.name, 'role': m.role}
                            for m in p.memberships.select_related('organisation')]}


@router.post('/auth/otp/verify', response=SessionOut, auth=None, summary='Check the code and get a session token')
def otp_verify(request, body: OtpVerifyIn):
    party, token, created = services.verify_otp(body.challenge_id, body.code, body.device)
    return {'token': token, 'new_account': created, 'me': me_out(party)}


@router.post('/auth/logout', response={204: None}, summary='Revoke this session token at once')
def logout(request):
    st = request.session_token
    st.revoked_at = timezone.now()
    st.save(update_fields=['revoked_at'])
    return Status(204, None)


@router.get('/me', response=MeOut)
def me(request):
    return me_out(party_of(request))


class ProfileIn(Schema):
    name: str | None = None
    works_at: str | None = None
    looking_for: str | None = None
    move_in_on: date | None = None
    guardian_name: str | None = None
    date_of_birth: str | None = None
    home_address: str | None = None
    emergency_contact: str | None = None


LIMITS = {'name': 80, 'works_at': 120, 'guardian_name': 80, 'home_address': 300}


def _check_profile(p, d: dict) -> None:
    """These details go on the police verification form, so they have to be real values."""
    from datetime import date as _date

    from apps.core.api_support import today
    for k, n in LIMITS.items():
        if k in d and len(d[k]) > n:
            raise ApiError(422, 'too_long', f'Keep {k.replace("_", " ")} under {n} characters.')
    if 'name' in d and len(d['name']) < 2:
        raise ApiError(422, 'name_needed', 'Enter your full name.')
    if d.get('date_of_birth'):
        try:
            dob = _date.fromisoformat(d['date_of_birth'])
        except ValueError:
            raise ApiError(422, 'bad_date', 'Enter your date of birth as YYYY-MM-DD.') from None
        age = (today() - dob).days / 365.25
        if not 15 <= age <= 100:
            raise ApiError(422, 'bad_date', 'Check your date of birth.')
        d['date_of_birth'] = dob.isoformat()
    if d.get('emergency_contact'):
        ph = services.normalise_phone(d['emergency_contact'])   # raises with a clear message if it isn't a mobile number
        if ph == p.phone:
            raise ApiError(422, 'own_number', 'Give someone else’s number for emergencies, like a parent’s.')
        d['emergency_contact'] = ph


@router.patch('/me', response=MeOut, summary='Update name, college or work, and the police-form details')
def update_me(request, body: ProfileIn):
    p = party_of(request)
    d = {k: v.strip() if isinstance(v, str) else v for k, v in body.model_dump(exclude_none=True).items()}
    _check_profile(p, d)
    if 'looking_for' in d and d['looking_for'] not in ('Boys', 'Girls', 'Co-ed'):
        raise ApiError(422, 'bad_choice', 'Choose Boys, Girls or Co-ed.')
    for k in ('name', 'works_at', 'looking_for', 'move_in_on'):
        if k in d:
            setattr(p, k, d.pop(k))
    if d:
        p.profile = {**(p.profile or {}), **d}
    p.save()
    return me_out(p)


class KycStartOut(Schema):
    txn: str
    redirect_url: str


@router.post('/kyc/digilocker/start', response=KycStartOut, summary='Start DigiLocker consent')
def kyc_start(request):
    return services.kyc_start(party_of(request))


class KycCompleteIn(Schema):
    txn: str
    auth_code: str


@router.post('/kyc/digilocker/complete', response=MeOut, summary='Finish DigiLocker; keeps only the last 4 Aadhaar digits')
def kyc_complete(request, body: KycCompleteIn):
    return me_out(services.kyc_complete(party_of(request), body.txn, body.auth_code))


__all__ = ['router', 'bearer']
