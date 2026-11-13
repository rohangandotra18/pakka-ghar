"""Public listings, and the owner's property setup (details, map pin, rooms, meters, papers, payouts)."""
import math
import re
import secrets
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone
from ninja import Router, Schema

from apps.core.api_support import OPTIONAL, ApiError, audit, owner_org, party_of
from apps.jurisdiction.rules import RULES, check_tariff

from . import services
from .models import OwnershipDocument, PayoutAccount, Property, Room

ROOM_KINDS = ('single', 'double', 'triple')
router = Router(tags=['listings'])
owner = Router(tags=['owner'])


class FreeBedOut(Schema):
    bed_id: int
    room: str
    bed: int
    kind: str
    rent_paise: int
    offers_open: bool


class RoomCardOut(Schema):
    number: str
    kind: str
    kind_label: str
    rent_paise: int
    beds: int
    free: int
    bidding: bool
    instant: bool = False   # instant booking: a verified tenant books without waiting for the owner
    cap_paise: int
    closes_at: datetime | None
    bids: int
    min_bid_paise: int | None
    max_bid_paise: int | None


class ListingPhotoOut(Schema):
    id: str
    url: str
    thumb: str
    room: str | None
    caption: str
    taken_at: datetime


class ListingOut(Schema):
    id: str
    name: str
    gender: str
    area: str
    city: str
    address: str
    meals: str
    lat: float
    lng: float
    rent_paise: int
    free: int
    rating: float | None
    stays: int
    hot: bool
    watching: int
    free_bed: FreeBedOut | None
    rooms: list[RoomCardOut]       # rooms with a free bed: what an application can ask for
    photos: list[ListingPhotoOut]  # all taken on site with the app's camera
    deposit_months: int
    notice_months: int
    tariff_paise: int
    verified_owner: bool
    taking_tenants: bool           # false while the trust team checks it or the owner has paused it
    move_in_on: date
    km: float | None


def _bbox(raw: str) -> tuple[float, float, float, float]:
    bad = ApiError(422, 'bad_bbox', 'The map area must be west,south,east,north in degrees, each side at most 1 degree.')
    try:
        west, south, east, north = (float(v) for v in raw.split(','))
    except ValueError:
        raise bad
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        raise bad
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90) or east - west > 1 or north - south > 1:
        raise bad
    return west, south, east, north


@router.get('/listings', response=list[ListingOut], auth=OPTIONAL, summary='Search published PGs near a place or inside a map area')
def search(request, lat: float | None = None, lng: float | None = None, radius_km: float = services.RADIUS_KM,
           gender: str | None = None, q: str | None = None, bbox: str | None = None, max_rent_paise: int | None = None,
           kind: str | None = None, free_only: bool = False, limit: int = 100):
    if not 0 < radius_km <= 25:
        raise ApiError(422, 'bad_radius', 'Radius must be between 0 and 25 km.')
    if (lat is None) != (lng is None) or (lat is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180)):  # also refuses NaN
        raise ApiError(422, 'bad_place', 'Send both lat and lng, as a real place.')
    area = _bbox(bbox) if bbox is not None else None
    if max_rent_paise is not None and max_rent_paise <= 0:
        raise ApiError(422, 'bad_filter', 'The most rent must be more than zero.')
    if kind is not None and kind not in ROOM_KINDS:
        raise ApiError(422, 'bad_filter', 'Room type must be single, double or triple.')
    if not 1 <= limit <= 200:
        raise ApiError(422, 'bad_filter', 'Ask for between 1 and 200 results.')
    q = ' '.join((q or '').split()[:6])[:100]  # a few words is a search; more is noise
    return services.search(lat, lng, radius_km, gender, q or None, bbox=area, max_rent_paise=max_rent_paise, kind=kind,
                           free_only=free_only, limit=limit)


class PlaceOut(Schema):
    id: int
    name: str
    kind: str
    city: str
    lat: float
    lng: float


@router.get('/places', response=list[PlaceOut], auth=OPTIONAL, summary='Sectors, colleges, hospitals and markets to jump the map to')
def places(request, q: str | None = None, limit: int = 8):
    if not 1 <= limit <= 20:
        raise ApiError(422, 'bad_filter', 'Ask for between 1 and 20 places.')
    found = services.places(q, limit)
    return [{'id': p.id, 'name': p.name, 'kind': p.kind, 'city': p.city, 'lat': float(p.lat), 'lng': float(p.lng)} for p in found]


@router.get('/listings/{slug}', response=ListingOut, auth=OPTIONAL, summary='One PG')
def detail(request, slug: str):
    found = services.by_slug(slug)
    if not found:
        raise ApiError(404, 'not_found', 'No such PG.')
    return found


# ---- owner: the property --------------------------------------------------------------------------------

class RoomOut(Schema):
    number: str
    kind: str
    rent_paise: int
    beds: int
    meter: str | None


class DocOut(Schema):
    kind: str
    label: str
    status: str


class PropertyOut(Schema):
    id: str
    name: str
    address: str
    area: str
    city: str
    gender: str
    meals: str
    lat: float | None
    lng: float | None
    status: str
    tariff_paise: int
    max_tariff_paise: int
    deposit_months: int
    notice_months: int
    rooms: list[RoomOut]
    documents: list[DocOut]
    payout: str | None
    no_cash_pledged: bool
    verified: bool
    review_note: str | None   # why the trust team last sent it back (shown while it is a draft)


def _prop(request) -> Property:
    org = owner_org(request)
    p = Property.objects.filter(organisation=org).order_by('created_at').first()
    if not p:
        raise ApiError(404, 'no_property', 'Add your property first.')
    return p


def property_out(p: Property) -> dict:
    pay = PayoutAccount.objects.filter(organisation=p.organisation).order_by('-created_at').first()
    return {
        'id': p.slug, 'name': p.name, 'address': p.address, 'area': p.area, 'city': p.city, 'gender': p.gender,
        'meals': p.meals, 'lat': float(p.lat) if p.lat is not None else None, 'lng': float(p.lng) if p.lng is not None else None,
        'status': p.status, 'tariff_paise': p.tariff_paise, 'max_tariff_paise': RULES[p.city].max_tariff_paise,
        'deposit_months': p.deposit_months, 'notice_months': p.notice_months,
        'rooms': [{'number': r.number, 'kind': r.kind, 'rent_paise': r.rent_paise, 'beds': r.beds.count(),
                   'meter': getattr(r, 'meter', None) and r.meter.model} for r in p.rooms.all()],
        'documents': [{'kind': d.kind, 'label': d.get_kind_display(), 'status': d.status} for d in p.documents.order_by('created_at')],
        'payout': f'{pay.account_masked} · {pay.bank_name}' if pay else None,
        'no_cash_pledged': p.organisation.no_cash_pledged_at is not None,
        'verified': p.organisation.verified_at is not None,
        'review_note': (p.attributes or {}).get('review_note'),
    }


@owner.get('/owner/property', response=PropertyOut)
def get_property(request):
    return property_out(_prop(request))


class NewPropertyIn(Schema):
    name: str
    address: str
    area: str
    city: str = 'chandigarh'
    gender: str = 'Boys'
    meals: str = '3 meals'


@owner.post('/owner/property', response=PropertyOut, summary='A new owner lists their first PG (starts as a draft)')
def new_property(request, body: NewPropertyIn):
    from django.utils.text import slugify

    from apps.core.models import Membership, Organisation
    from apps.core.rls import set_context
    party = party_of(request)
    if request.org:
        raise ApiError(409, 'already_listed', 'You already have a property. Edit it instead.')
    if body.city not in RULES or body.gender not in ('Boys', 'Girls', 'Co-ed'):
        raise ApiError(422, 'bad_property', 'Check the city and who the PG is for.')
    org = Organisation.objects.create(name=body.name)
    Membership.objects.create(party=party, organisation=org, role='owner')
    request.org = org
    set_context(org.id, party.id)
    slug = slugify(body.name)[:50] or 'pg'
    if Property.objects.filter(slug=slug).exists() or _slug_taken(slug):
        slug = f'{slug}-{secrets.token_hex(2)}'
    p = Property.objects.create(organisation=org, slug=slug, name=body.name, address=body.address, area=body.area,
                                city=body.city, gender=body.gender, meals=body.meals)
    for kind in ('sale_deed', 'property_tax', 'pg_registration'):
        OwnershipDocument.objects.create(organisation=org, property=p, kind=kind, status='later')
    audit(org, party, 'property.create', p, after={'name': p.name})
    return property_out(p)


def _slug_taken(slug: str) -> bool:
    from apps.core.rls import system
    with system():
        return Property.objects.filter(slug=slug).exists()


class RoomsIn(Schema):
    kind: str          # single | double | triple
    rooms: int
    rent_paise: int
    first_number: int = 101


@owner.post('/owner/rooms', response=PropertyOut, summary='Add rooms of one type, with their beds')
def add_rooms(request, body: RoomsIn):
    from .models import Bed
    p = _prop(request)
    per = {'single': 1, 'double': 2, 'triple': 3}.get(body.kind)
    if not per or not 1 <= body.rooms <= 60 or not 100000 <= body.rent_paise <= 10000000:
        raise ApiError(422, 'bad_rooms', 'Check the room type, count and rent.')
    n = body.first_number
    for _ in range(body.rooms):
        while Room.objects.filter(property=p, number=str(n)).exists():
            n += 1
        room = Room.objects.create(organisation=p.organisation, property=p, number=str(n), kind=body.kind, rent_paise=body.rent_paise)
        Bed.objects.bulk_create([Bed(organisation=p.organisation, room=room, label=i + 1) for i in range(per)])
    audit(p.organisation, request.party, 'rooms.add', p, after=body.model_dump())
    return property_out(p)


@owner.post('/owner/documents/{kind}', response=PropertyOut, summary='Record an uploaded ownership paper')
def upload_doc(request, kind: str, file_name: str = ''):
    p = _prop(request)
    if kind not in dict(OwnershipDocument.KINDS):
        raise ApiError(422, 'bad_kind', 'Unknown document.')
    d, _ = OwnershipDocument.objects.get_or_create(property=p, kind=kind, defaults={'organisation': p.organisation})
    before = {'status': d.status, 'file_name': d.file_name}
    d.status, d.file_name = 'uploaded', file_name[:200]
    d.save()
    audit(p.organisation, request.party, 'document.upload', d, before, {'status': d.status, 'file_name': d.file_name})
    return property_out(p)


class PropertyIn(Schema):
    name: str | None = None
    address: str | None = None
    area: str | None = None
    city: str | None = None
    gender: str | None = None
    meals: str | None = None
    tariff_paise: int | None = None


@owner.patch('/owner/property', response=PropertyOut, summary='Edit details; every change is audited')
def edit_property(request, body: PropertyIn):
    p = _prop(request)
    changes = body.model_dump(exclude_none=True)
    if 'gender' in changes and changes['gender'] not in ('Boys', 'Girls', 'Co-ed'):
        raise ApiError(422, 'bad_gender', 'Choose Boys, Girls or Co-ed.')
    if 'city' in changes and changes['city'] not in RULES:
        raise ApiError(422, 'bad_city', 'Pakka Ghar works in Chandigarh, Mohali and Panchkula.')
    if 'tariff_paise' in changes:
        try:
            check_tariff(changes.get('city', p.city), changes['tariff_paise'])
        except ValueError as e:
            raise ApiError(422, 'tariff_above_discom', str(e))
    before = {k: getattr(p, k) for k in changes}
    for k, v in changes.items():
        setattr(p, k, v)
    p.save()
    audit(p.organisation, request.party, 'property.edit', p, before, changes)
    changed = {k for k in changes if before[k] != changes[k]}
    if changed & CHECKED_DETAILS:
        _recheck(request, p, 'changed ' + ', '.join(sorted(changed & CHECKED_DETAILS)))
    return property_out(p)


# What the trust team verified. Changing any of these on a live PG sends it back for a check, so a verified
# listing can't be switched to another building or name.
CHECKED_DETAILS = {'name', 'address', 'area', 'city'}
PIN_MOVE_RECHECK_M = 150


def _recheck(request, p, why: str) -> None:
    if p.status != 'published':
        return   # a draft or one already waiting is checked anyway
    p.status = 'submitted'
    p.attributes = {**(p.attributes or {}), 'recheck': why}
    p.save(update_fields=['status', 'attributes', 'updated_at'])
    audit(p.organisation, request.party, 'property.recheck', p, after={'why': why})
    from apps.core.api_support import notify
    notify(request.party, 'property.recheck', f'{p.name} is with the trust team again because you {why}. Residents aren’t affected; new tenants see it once it’s checked.',
           org=p.organisation)


class PinIn(Schema):
    lat: float
    lng: float


@owner.put('/owner/property/pin', response=PropertyOut, summary='Pin the exact building on the map')
def pin(request, body: PinIn):
    if not (30.55 <= body.lat <= 30.85 and 76.60 <= body.lng <= 77.00):
        raise ApiError(422, 'outside_tricity', 'That point is outside Chandigarh, Mohali and Panchkula.')
    p = _prop(request)
    before = {'lat': str(p.lat), 'lng': str(p.lng)}
    moved_m = None
    if p.lat is not None and p.lng is not None:
        from .photos import km
        moved_m = km(float(p.lat), float(p.lng), body.lat, body.lng) * 1000
    p.lat, p.lng = Decimal(f'{body.lat:.6f}'), Decimal(f'{body.lng:.6f}')
    p.save(update_fields=['lat', 'lng', 'updated_at'])
    audit(p.organisation, request.party, 'property.pin', p, before, {'lat': str(p.lat), 'lng': str(p.lng)})
    if moved_m is not None and moved_m > PIN_MOVE_RECHECK_M:
        _recheck(request, p, f'moved the pin {moved_m:,.0f} m')
    return property_out(p)


@owner.post('/owner/rooms/{number}/meter', response=PropertyOut, summary='Pair the Wi-Fi meter in a room')
def pair_meter(request, number: str):
    from .models import Meter
    p = _prop(request)
    room = Room.objects.filter(property=p, number=number).first()
    if not room:
        raise ApiError(404, 'no_room', f'No room {number}.')
    Meter.objects.get_or_create(room=room, defaults={'organisation': p.organisation, 'device_id': 'QUBE-' + secrets.token_hex(4).upper()})
    return property_out(p)


IFSC = re.compile(r'[A-Z]{4}0[A-Z0-9]{6}')


class PayoutIn(Schema):
    bank_name: str
    account_number: str
    ifsc: str


@owner.post('/owner/payout', response=PropertyOut, summary='Where rent is paid; checked with a ₹1 test deposit')
def payout(request, body: PayoutIn):
    p = _prop(request)
    digits = ''.join(ch for ch in body.account_number if ch.isdigit())
    ifsc = body.ifsc.strip().upper()
    # Indian accounts are 9 to 18 digits; an IFSC is four letters for the bank, a zero, then six for the branch
    if not 9 <= len(digits) <= 18 or not IFSC.fullmatch(ifsc):
        raise ApiError(422, 'bad_account', 'Check the account number and IFSC.')
    before = PayoutAccount.objects.filter(organisation=p.organisation).order_by('-created_at').first()
    acct = PayoutAccount.objects.create(organisation=p.organisation, bank_name=body.bank_name.strip()[:80], ifsc=ifsc,
                                        account_masked='XXXX XXXX ' + digits[-4:], name_matched_at=timezone.now())
    # where the rent goes is the change a stolen login would make: keep a trail and tell every owner of the PG
    audit(p.organisation, request.party, 'payout.change', acct,
          {'account': before.account_masked, 'ifsc': before.ifsc} if before else None,
          {'account': acct.account_masked, 'ifsc': acct.ifsc, 'bank': acct.bank_name})
    from apps.booking.common import owners_of
    from apps.core.api_support import notify
    for o in owners_of(p.organisation):
        notify(o, 'payout.changed', f'Rent for {p.name} will now be paid to {acct.bank_name} {acct.account_masked}. '
               'If this wasn’t you, contact the trust team.', org=p.organisation)
    return property_out(p)


@owner.post('/owner/no-cash-pledge', response=PropertyOut, summary="The owner's promise to take no cash")
def no_cash(request):
    p = _prop(request)
    org = p.organisation
    if not org.no_cash_pledged_at:
        org.no_cash_pledged_at = timezone.now()
        org.save(update_fields=['no_cash_pledged_at'])
        audit(org, request.party, 'org.no_cash_pledge', org)
    return property_out(p)


@owner.post('/owner/property/submit', response=PropertyOut, summary='Send papers to the trust team')
def submit(request):
    p = _prop(request)
    party_of(request)
    missing = [m for m, ok in [('the map pin', p.lat is not None), ('the no-cash promise', p.organisation.no_cash_pledged_at),
                               ('ownership papers', OwnershipDocument.objects.filter(property=p, kind__in=['sale_deed', 'lease'], status__in=['uploaded', 'accepted']).exists())] if not ok]
    if missing:
        raise ApiError(422, 'incomplete', 'Still needed: ' + ', '.join(missing) + '.')
    if p.status == 'draft':
        p.status = 'submitted'
        p.save(update_fields=['status', 'updated_at'])
        audit(p.organisation, request.party, 'property.submit', p)
    return property_out(p)
