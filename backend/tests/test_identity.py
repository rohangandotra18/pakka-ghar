"""Sign-in, AC-19 instant revocation, and zero-disclosure ID."""
from apps.core.rls import system
from apps.identity.models import OtpChallenge

from .conftest import Api


def test_otp_sign_in_and_wrong_codes_count(world):
    api = Api()
    ch = api.post('/auth/otp/start', {'phone': '98765 43210'}).json()
    assert ch['phone'] == '+919876543210'
    for _ in range(5):
        assert api.post('/auth/otp/verify', {'challenge_id': ch['challenge_id'], 'code': '000000' if ch['dev_code'] != '000000' else '111111'}).status_code == 400
    with system():
        assert OtpChallenge.objects.get(pk=ch['challenge_id']).attempts == 5   # kept although each request failed
    r = api.post('/auth/otp/verify', {'challenge_id': ch['challenge_id'], 'code': ch['dev_code']})
    assert r.status_code == 429


def test_logout_revokes_at_once(world):
    ch = Api().post('/auth/otp/start', {'phone': '+91 98765 43210'}).json()
    tok = Api().post('/auth/otp/verify', {'challenge_id': ch['challenge_id'], 'code': ch['dev_code']}).json()['token']
    me = Api(tok)
    assert me.get('/me').status_code == 200
    assert me.post('/auth/logout').status_code == 204
    assert me.get('/me').status_code == 401


def test_bad_phone_numbers(world):
    assert Api().post('/auth/otp/start', {'phone': '12345'}).status_code == 422


def test_digilocker_keeps_only_last_four(world):
    api = world['api'](world['unverified'])
    txn = api.post('/kyc/digilocker/start').json()['txn']
    me = api.post('/kyc/digilocker/complete', {'txn': txn, 'auth_code': 'x'}).json()
    assert me['verified'] and me['aadhaar_masked'].startswith('XXXXXXXX') and len(me['aadhaar_masked']) == 12


def test_a_number_takes_only_so_many_wrong_codes_a_day(world, settings):
    from datetime import timedelta

    from django.utils import timezone
    phone = '+919800055555'
    with system():   # earlier today: enough fresh codes, each guessed wrong to the limit
        for _ in range(settings.OTP_WRONG_PER_PHONE_DAY // settings.OTP_MAX_ATTEMPTS):
            OtpChallenge.objects.create(phone=phone, code_hash='x', expires_at=timezone.now(), attempts=settings.OTP_MAX_ATTEMPTS)
        OtpChallenge.objects.filter(phone=phone).update(created_at=timezone.now() - timedelta(hours=3))
    r = Api().post('/auth/otp/start', {'phone': '98000 55555'})
    assert r.status_code == 429 and r.json()['code'] == 'too_many_wrong_codes'
    with system():   # a day later they no longer count
        OtpChallenge.objects.filter(phone=phone).update(created_at=timezone.now() - timedelta(hours=25))
    assert Api().post('/auth/otp/start', {'phone': '98000 55555'}).status_code == 200
