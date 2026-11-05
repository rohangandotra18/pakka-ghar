"""Agreements: the owner's PDF or the standard one, read in full, signed with typed name + one-time code by both."""
import io
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction

from apps.booking.models import Agreement, Booking
from apps.core.rls import system
from apps.payments.models import Payment
from apps.payments.services import simulate_capture

from .conftest import read, token_for
from .helpers import accepted


@pytest.fixture(autouse=True)
def _private(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path


def _owner_pdf(pages=2):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.drawString(72, 720, f'Sidhu Boys PG house rules, page {i + 1}: no smoking, gate closes 11 pm.')
        c.showPage()
    c.save()
    return buf.getvalue()


def _paid_booking(world, tenant):
    api = accepted(world, tenant, world['owner_a'])
    b = api.post('/bookings', {'listing': 'sidhu'}, idem=uuid.uuid4().hex).json()
    pay = api.post(f"/bookings/{b['id']}/deposit", idem=uuid.uuid4().hex).json()
    with system():
        simulate_capture(Payment.objects.get(pk=pay['id']))
    return api, b['id']


def _sign(api, bid, name, pages):
    st = api.post(f'/agreements/{bid}/sign/start', {'pages_read': pages}).json()
    return api.post(f'/agreements/{bid}/sign', {'challenge_id': st['challenge_id'], 'code': st['dev_code'], 'typed_name': name, 'pages_read': pages})


def test_standard_agreement_read_and_signed_by_both(world):
    tenant, bid = _paid_booking(world, world['simran'])
    owner = world['api'](world['owner_a'])
    doc = tenant.get(f'/agreements/{bid}').json()
    assert doc['source'] == 'standard' and doc['pages'] >= 1 and doc['my_role'] == 'tenant'
    page = tenant.get(doc['page_urls'][0].removeprefix('/api'))
    assert len(doc['page_urls']) == doc['pages'] and page.status_code == 200 and page['Content-Type'] == 'image/jpeg' and len(page.content) > 5000
    assert tenant.post(f'/agreements/{bid}/sign/start', {'pages_read': 0}).json()['code'] == 'read_all'
    assert owner.post(f'/agreements/{bid}/sign/start', {'pages_read': doc['pages']}).json()['code'] == 'tenant_signs_first'
    assert _sign(tenant, bid, 'Someone Else', doc['pages']).json()['code'] == 'name_mismatch'
    st = tenant.post(f'/agreements/{bid}/sign/start', {'pages_read': doc['pages']}).json()
    bad = tenant.post(f'/agreements/{bid}/sign', {'challenge_id': st['challenge_id'], 'code': '000000' if st['dev_code'] != '000000' else '111111', 'typed_name': 'simran  KAUR', 'pages_read': doc['pages']})
    assert bad.json()['code'] == 'wrong_code'
    ok = tenant.post(f'/agreements/{bid}/sign', {'challenge_id': st['challenge_id'], 'code': st['dev_code'], 'typed_name': 'simran  KAUR', 'pages_read': doc['pages']}).json()
    assert [s['role'] for s in ok['signatures']] == ['tenant'] and not ok['signed']
    assert owner.get(f'/agreements/{bid}').json()['my_role'] == 'owner'
    done = _sign(owner, bid, 'Jatinder Sidhu', doc['pages']).json()
    assert done['signed'] and done['signed_pages'] == doc['pages'] + 1 and {s['role'] for s in done['signatures']} == {'tenant', 'owner'}
    assert len(done['page_urls']) == done['signed_pages']
    cert = tenant.get(done['page_urls'][-1].removeprefix('/api'))
    assert cert.status_code == 200
    pdf = tenant.get(f'/agreements/{bid}/pdf')
    assert pdf['Content-Type'] == 'application/pdf' and b'%PDF' in pdf.content[:8]
    a = read(lambda: Agreement.objects.get(booking_id=bid))
    assert a.signed_sha256 and a.signatures.count() == 2 and all(s.document_sha256 == a.document_sha256 for s in a.signatures.all())
    assert tenant.post(f'/bookings/{bid}/stamp').json()['agreement']['stamped']
    with system(), pytest.raises(DatabaseError, match='append-only'), transaction.atomic(), connection.cursor() as c:
        c.execute("UPDATE booking_signature SET typed_name = 'forged'")


def test_owner_uploads_their_own_agreement(world):
    from django.test import Client
    c = Client()
    auth = {'HTTP_AUTHORIZATION': f'Bearer {token_for(world["owner_a"])}'}
    assert c.post('/api/owner/agreement-template', {'file': SimpleUploadedFile('a.txt', b'hello', 'text/plain')}, **auth).json()['code'] == 'not_pdf'
    r = c.post('/api/owner/agreement-template', {'file': SimpleUploadedFile('rules.pdf', _owner_pdf(2), 'application/pdf'), 'name': 'Sidhu PG agreement'}, **auth)
    assert r.status_code == 200 and r.json()['pages'] == 2
    tenant, bid = _paid_booking(world, world['simran'])
    doc = tenant.get(f'/agreements/{bid}').json()
    assert doc['source'] == 'owner' and doc['pages'] >= 3          # the filled-in cover page, then the owner's 2 pages
    assert tenant.get(doc['page_urls'][-1].removeprefix('/api')).status_code == 200


def test_only_the_two_parties_can_read_it(world):
    _, bid = _paid_booking(world, world['simran'])
    for stranger in (world['aman'], world['owner_b']):
        assert world['api'](stranger).get(f'/agreements/{bid}').status_code == 404
        assert world['api'](stranger).get(f'/agreements/{bid}/pages/1').status_code == 401     # no link, no page
    # a link opens only the page, copy and agreement it was issued for, and can't be forged
    tenant = world['api'](world['simran'])
    link = tenant.get(f'/agreements/{bid}').json()['page_urls'][0].removeprefix('/api')
    assert tenant.get(link).status_code == 200
    assert tenant.get(link.replace('/pages/1?', '/pages/2?')).status_code == 401
    assert tenant.get(link.replace('signed=false', 'signed=true')).status_code == 401
    assert tenant.get(link[:-3] + ('aaa' if link[-3:] != 'aaa' else 'bbb')).status_code == 401
    assert read(lambda: Booking.objects.get(pk=bid).agreement.document.name).startswith('agreements/')
