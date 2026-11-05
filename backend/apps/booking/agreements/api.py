"""Agreement API: read pages by signed link, sign, download; the owner's own agreement template."""
import hashlib
import io

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.utils import timezone
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from apps.booking.agreements.document import build_document, render_page
from apps.booking.agreements.signing import confirm_signing, start_signing
from apps.core.api_support import ApiError, audit, owner_org, party_of
from apps.core.rls import system

from ..models import Agreement, AgreementTemplate

router = Router(tags=['agreements'])


# ---- the API ----------------------------------------------------------------------------------------------

class SignatureOut(Schema):
    role: str
    name: str
    signed_at: str


class AgreementDocOut(Schema):
    booking_id: str
    pages: int
    source: str
    sha256: str
    signatures: list[SignatureOut]
    signed: bool               # both have signed; the pages now include the certificate
    signed_pages: int
    my_role: str
    page_urls: list[str]       # signed links to each page, valid 15 minutes; work as plain image URLs on every platform


PAGE_LINK_SALT, PAGE_LINK_AGE = 'agreement-page', 15 * 60


def page_link(a: Agreement, n: int, signed: bool, party_id) -> str:
    """A link to one page that works without a header, so phones and browsers can load it as an ordinary image.
    It names the booking, the page, the copy and the person it was issued to, and expires in 15 minutes."""
    tok = signing.dumps([str(a.booking_id), n, signed, str(party_id)], salt=PAGE_LINK_SALT, compress=True)
    return f'/api/agreements/{a.booking_id}/pages/{n}?signed={"true" if signed else "false"}&k={tok}'


def doc_out(a: Agreement, role: str, party_id) -> dict:
    sigs = list(a.signatures.all())
    signed = bool(a.signed_document)
    total = a.pages + 1 if signed else a.pages
    return {'booking_id': str(a.booking_id), 'pages': a.pages, 'source': a.source, 'sha256': a.document_sha256,
            'signatures': [{'role': s.role, 'name': s.typed_name, 'signed_at': s.signed_at.isoformat()} for s in sigs],
            'signed': signed, 'signed_pages': total, 'my_role': role,
            'page_urls': [page_link(a, n, signed, party_id) for n in range(1, total + 1)]}


def _for(request, booking_id) -> tuple[Agreement, str]:
    """The agreement, if the caller is its resident or the owner; row-level security decides what's found."""
    party = party_of(request)
    a = Agreement.objects.select_related('booking__guest', 'booking__bed__room__property').filter(booking_id=booking_id).first()
    if not a:
        raise ApiError(404, 'not_found', 'No such agreement.')
    if a.tenant_id == party.id:
        return a, 'tenant'
    if request.org and a.organisation_id == request.org.id:
        return a, 'owner'
    raise ApiError(404, 'not_found', 'No such agreement.')


@router.get('/agreements/{booking_id}', response=AgreementDocOut, summary='The agreement to read: pages, who has signed')
def get_doc(request, booking_id: str):
    a, role = _for(request, booking_id)
    if not a.document:
        with system():
            build_document(Agreement.objects.select_related('booking__bed__room__property', 'booking__guest').get(pk=a.pk))
        a.refresh_from_db()
    return doc_out(a, role, party_of(request).id)


@router.get('/agreements/{booking_id}/pages/{n}', auth=None, summary='One page as an image (JPEG), by the signed link from the agreement')
def page(request, booking_id: str, n: int, k: str = '', signed: bool = False):
    """Only the two people on the agreement get links (from GET /agreements/{id}); a link is checked here for its
    booking, page, copy and expiry, so it can't be reused for another page or another agreement."""
    try:
        b, pn, ps, _party = signing.loads(k, salt=PAGE_LINK_SALT, max_age=PAGE_LINK_AGE)
    except signing.SignatureExpired:
        raise ApiError(410, 'link_expired', 'This page link has expired. Reopen the agreement.')
    except signing.BadSignature:
        raise ApiError(401, 'unauthorised', 'Open the agreement in the app to read it.')
    if b != str(booking_id) or pn != n or ps != signed:
        raise ApiError(401, 'unauthorised', 'Open the agreement in the app to read it.')
    with system():
        a = Agreement.objects.filter(booking_id=booking_id).first()
        if not a:
            raise ApiError(404, 'not_found', 'No such agreement.')
        body = render_page(a, n, signed)
    resp = HttpResponse(body, content_type='image/jpeg')
    resp['Cache-Control'] = 'private, max-age=900'
    resp['Referrer-Policy'] = 'no-referrer'
    return resp


@router.get('/agreements/{booking_id}/pdf', summary='The PDF (the signed copy once both have signed)')
def pdf(request, booking_id: str):
    a, _ = _for(request, booking_id)
    f = a.signed_document or a.document
    with f.open('rb') as fh:
        resp = HttpResponse(fh.read(), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{a.booking.reference}{"-signed" if a.signed_document else ""}.pdf"'
    return resp


class StartIn(Schema):
    pages_read: int


class StartOut(Schema):
    challenge_id: str
    phone_last4: str
    dev_code: str | None = None


@router.post('/agreements/{booking_id}/sign/start', response=StartOut, summary='Send the signing code to your phone')
def sign_start(request, booking_id: str, body: StartIn):
    a, role = _for(request, booking_id)
    ch, code = start_signing(a, request.party, role, body.pages_read)
    return {'challenge_id': str(ch.id), 'phone_last4': request.party.phone[-4:], 'dev_code': code if settings.DEV_ECHO_OTP else None}


class ConfirmIn(Schema):
    challenge_id: str
    code: str
    typed_name: str
    pages_read: int


@router.post('/agreements/{booking_id}/sign', response=AgreementDocOut, summary='Sign: your typed name and the code')
def sign_confirm(request, booking_id: str, body: ConfirmIn):
    from apps.core.middleware import client_ip
    a, role = _for(request, booking_id)
    a = confirm_signing(a, request.party, role, body.challenge_id, body.code, body.typed_name, body.pages_read,
                        client_ip(request) or None, request.headers.get('User-Agent', ''))
    return doc_out(a, role, request.party.id)


# ---- the owner's own agreement ---------------------------------------------------------------------------------

class TemplateOut(Schema):
    name: str
    pages: int
    uploaded_at: str


@router.get('/owner/agreement-template', response=TemplateOut | None, tags=['owner'], summary='Your own agreement, if you uploaded one')
def get_template(request):
    from apps.property.models import Property
    org = owner_org(request)
    t = AgreementTemplate.objects.filter(property__in=Property.objects.filter(organisation=org), active=True).order_by('-created_at').first()
    return {'name': t.name, 'pages': t.pages, 'uploaded_at': t.created_at.isoformat()} if t else None


@router.post('/owner/agreement-template', response=TemplateOut, tags=['owner'], summary='Upload your own agreement (PDF); new bookings use it')
def upload_template(request, file: UploadedFile = File(...), name: str = Form('')):
    from pypdf import PdfReader

    from apps.property.models import Property
    org = owner_org(request)
    prop = Property.objects.filter(organisation=org).order_by('created_at').first()
    if not prop:
        raise ApiError(404, 'no_property', 'Add your property first.')
    raw = file.read()
    if len(raw) > settings.AGREEMENT_MAX_BYTES:
        raise ApiError(413, 'too_big', 'That file is over 10 MB.')
    if not raw.startswith(b'%PDF'):
        raise ApiError(422, 'not_pdf', 'Upload the agreement as a PDF.')
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ApiError(422, 'locked', 'That PDF is password-protected. Upload an unlocked copy.')
        pages = len(reader.pages)
    except ApiError:
        raise
    except Exception:  # noqa: BLE001 - an unreadable PDF
        raise ApiError(422, 'not_pdf', 'That PDF can’t be read.')
    if not 1 <= pages <= settings.AGREEMENT_MAX_PAGES:
        raise ApiError(422, 'too_long', f'Keep the agreement to {settings.AGREEMENT_MAX_PAGES} pages.')
    AgreementTemplate.objects.filter(property=prop, active=True).update(active=False, updated_at=timezone.now())
    t = AgreementTemplate(organisation=org, property=prop, name=(name or file.name or 'Agreement')[:120],
                          sha256=hashlib.sha256(raw).hexdigest(), pages=pages, uploaded_by=request.party)
    t.file.save(f'{prop.slug}-{timezone.now():%Y%m%d%H%M%S}.pdf', ContentFile(raw), save=False)
    t.save()
    audit(org, request.party, 'agreement.template', t, after={'pages': pages, 'sha256': t.sha256})
    return {'name': t.name, 'pages': t.pages, 'uploaded_at': t.created_at.isoformat()}


@router.post('/owner/agreement-template/remove', response=dict, tags=['owner'], summary='Go back to the standard agreement')
def remove_template(request):
    from apps.property.models import Property
    org = owner_org(request)
    AgreementTemplate.objects.filter(property__in=Property.objects.filter(organisation=org), active=True).update(active=False, updated_at=timezone.now())
    return {'ok': True}
