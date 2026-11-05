"""Photos are taken in the app with the phone's camera, at the building, moments before upload. Nothing from a
gallery, another place, another day, an editor or an image generator is accepted.

What the server checks on each upload:
  - the phone's GPS fix (sent with the photo) is within PHOTO_MAX_DISTANCE_M of the owner's pin, with a usable accuracy
  - the camera's timestamp is within the last PHOTO_MAX_AGE_S (so a saved or downloaded picture can't be used)
  - the file is a real photo Pillow can decode, not a copy already uploaded here, and its metadata names no editing
    or image-generation software
Each accepted photo is re-encoded as JPEG with all metadata stripped (no hidden location or payloads) plus a thumbnail.
The app only offers the camera; there is no gallery picker.
"""
import hashlib
import io
import math
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from apps.core.api_support import ApiError, audit, owner_org, party_of

from .models import Photo, Property, Room

router = Router(tags=['photos'])

AI_OR_EDITOR = ('dall', 'midjourney', 'stable diffusion', 'firefly', 'imagen', 'gemini', 'chatgpt', 'openai', 'sora',
                'photoshop', 'lightroom', 'gimp', 'snapseed', 'picsart', 'canva', 'facetune', 'remini')


def km(lat1, lng1, lat2, lng2) -> float:
    r = math.pi / 180
    h = math.sin((lat2 - lat1) * r / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lng2 - lng1) * r / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _check_and_encode(raw: bytes) -> tuple[bytes, bytes, tuple[int, int]]:
    from PIL import Image, ImageOps
    if len(raw) > settings.PHOTO_MAX_BYTES:
        raise ApiError(413, 'too_big', 'That photo is too large. Take it again at normal quality.')
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw))
    except Exception:  # noqa: BLE001 - anything Pillow can't read isn't a photo
        raise ApiError(422, 'not_a_photo', 'That file isn’t a photo.')
    exif = img.getexif()
    software = ' '.join(str(exif.get(t, '')) for t in (0x0131, 0x013B, 0x9286)).lower()  # Software, Artist, UserComment
    if any(k in software for k in AI_OR_EDITOR):
        raise ApiError(422, 'edited', 'This photo was edited or generated. Take a fresh one with the camera.')
    if min(img.size) < 480:
        raise ApiError(422, 'too_small', 'That photo is too small. Take it again with the camera.')
    img = ImageOps.exif_transpose(img).convert('RGB')
    img.thumbnail((2000, 2000))
    dims = img.size
    full = io.BytesIO()
    img.save(full, 'JPEG', quality=82, optimize=True)   # a clean JPEG: no EXIF, no GPS, nothing appended
    img.thumbnail((480, 480))
    thumb = io.BytesIO()
    img.save(thumb, 'JPEG', quality=78, optimize=True)
    return full.getvalue(), thumb.getvalue(), dims


def save_photo(prop: Property, who, raw: bytes, taken_at: datetime, lat: float, lng: float, accuracy_m: float,
               device: str = '', room: Room | None = None, caption: str = '', ticket=None) -> Photo:
    if prop.lat is None or prop.lng is None:
        raise ApiError(409, 'pin_first', 'Pin the building on the map before adding photos.')
    now = timezone.now()
    if taken_at > now + timedelta(minutes=2) or now - taken_at > timedelta(seconds=settings.PHOTO_MAX_AGE_S):
        raise ApiError(422, 'not_fresh', 'Photos must be taken just now with the camera in the app.')
    if not 0 <= accuracy_m <= settings.PHOTO_MAX_ACCURACY_M:
        raise ApiError(422, 'weak_location', 'Your phone’s location is too rough. Step outside or wait a moment, then try again.')
    dist = km(float(prop.lat), float(prop.lng), lat, lng) * 1000
    if dist > settings.PHOTO_MAX_DISTANCE_M:
        raise ApiError(422, 'not_on_site', f'You’re {dist / 1000:.1f} km from {prop.name}. Photos must be taken at the building.')
    digest = hashlib.sha256(raw).hexdigest()
    if Photo.objects.filter(property=prop, sha256=digest).exists():
        raise ApiError(409, 'duplicate', 'That photo is already here.')
    full, thumb, (w, h) = _check_and_encode(raw)
    p = Photo(id=uuid.uuid4(), organisation=prop.organisation, property=prop, room=room, ticket=ticket, taken_by=who,
              sha256=digest, caption=caption.strip()[:80], taken_at=taken_at, lat=Decimal(f'{lat:.6f}'), lng=Decimal(f'{lng:.6f}'),
              accuracy_m=round(accuracy_m), distance_m=round(dist), device=device[:80], width=w, height=h)
    p.image.save('photo.jpg', ContentFile(full), save=False)
    p.thumb.save('thumb.jpg', ContentFile(thumb), save=False)
    p.save()
    audit(prop.organisation, who, 'photo.add', p, after={'distance_m': p.distance_m, 'ticket': str(ticket.id) if ticket else None})
    return p


class PhotoOut(Schema):
    id: uuid.UUID
    url: str
    thumb: str
    room: str | None
    caption: str
    taken_at: datetime
    distance_m: int


def photo_out(p: Photo) -> dict:
    return {'id': p.id, 'url': p.image.url, 'thumb': p.thumb.url if p.thumb else p.image.url, 'room': p.room.number if p.room else None,
            'caption': p.caption, 'taken_at': p.taken_at, 'distance_m': p.distance_m}


def _owner_prop(request) -> Property:
    org = owner_org(request)
    p = Property.objects.filter(organisation=org).order_by('created_at').first()
    if not p:
        raise ApiError(404, 'no_property', 'Add your property first.')
    return p


@router.post('/owner/photos', response=PhotoOut, tags=['owner'], summary='Add a photo taken just now at the building')
def add_listing_photo(request, file: UploadedFile = File(...), taken_at: datetime = Form(...), lat: float = Form(...),
                      lng: float = Form(...), accuracy_m: float = Form(...), room: str = Form(''), caption: str = Form(''),
                      device: str = Form('')):
    prop = _owner_prop(request)
    r = Room.objects.filter(property=prop, number=room).first() if room else None
    if room and not r:
        raise ApiError(404, 'no_room', f'No room {room}.')
    p = save_photo(prop, request.party, file.read(), taken_at, lat, lng, accuracy_m, device, r, caption)
    return photo_out(p)


@router.get('/owner/photos', response=list[PhotoOut], tags=['owner'])
def list_photos(request):
    prop = _owner_prop(request)
    return [photo_out(p) for p in Photo.objects.filter(property=prop, ticket__isnull=True, status='live').select_related('room')]


@router.post('/owner/photos/{photo_id}/remove', response=list[PhotoOut], tags=['owner'])
def remove_photo(request, photo_id: uuid.UUID):
    prop = _owner_prop(request)
    Photo.objects.filter(pk=photo_id, property=prop).update(status='removed', updated_at=timezone.now())
    return list_photos(request)


@router.post('/requests/{ticket_id}/photos', response=PhotoOut, tags=['requests'], summary='Add a photo of the problem, taken just now in your room')
def add_ticket_photo(request, ticket_id: uuid.UUID, file: UploadedFile = File(...), taken_at: datetime = Form(...),
                     lat: float = Form(...), lng: float = Form(...), accuracy_m: float = Form(...), device: str = Form('')):
    from apps.maintenance.models import Ticket
    party = party_of(request)
    t = Ticket.objects.filter(pk=ticket_id, raised_by=party).select_related('property').first()
    if not t:
        raise ApiError(404, 'not_found', 'No such request.')
    p = save_photo(t.property, party, file.read(), taken_at, lat, lng, accuracy_m, device, t.room, '', ticket=t)
    return photo_out(p)
