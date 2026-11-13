"""Listings as tenants see them. Availability and ratings span everyone's bookings, so the aggregates are read
with the system role and only public fields leave this module."""
import math
import re
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Case, Count, F, IntegerField, Max, Min, Q, When
from django.utils import timezone

from apps.core.api_support import add_months, ist, month_start, today
from apps.core.rls import system

from .models import Bed, Place, Property

RADIUS_KM = 3.0


def km_between(lat1, lng1, lat2, lng2) -> float:
    r = math.pi / 180
    dlat, dlng = (lat2 - lat1) * r, (lng2 - lng1) * r
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin(dlng / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def next_move_in():
    """Beds are let from the 1st of a month: the coming 1st, or today if it is the 1st."""
    t = today()
    return t if t.day == 1 else add_months(month_start(t), 1)


def offer_cap_paise(rent_paise: int) -> int:
    """15% over the listed rent, rounded to the nearest ₹50."""
    return round(rent_paise * 1.15 / 5000) * 5000


def revealed(qs, cutoff=None):
    """Ratings that may be shown: both sides have rated, or 14 days have passed. EXISTS, not a join, so no rating is
    counted twice in an average."""
    from django.db.models import Exists, OuterRef

    from apps.booking.models import Rating
    cutoff = cutoff or timezone.now() - timedelta(days=14)
    other = Rating.objects.filter(booking=OuterRef('booking')).exclude(direction=OuterRef('direction'))
    return qs.filter(Q(created_at__lt=cutoff) | Q(Exists(other)))


def listings(props: list[Property], near: tuple[float, float] | None = None) -> list[dict]:
    """The public cards for several PGs in a fixed number of queries, however many PGs there are. Call inside system()."""
    from apps.booking.models import BLOCKING, Application, Booking, Rating, Visit
    from .models import Room
    if not props:
        return []
    ids = [p.id for p in props]
    start = next_move_in()
    lo, hi = ist(start), ist(add_months(start, 1))
    beds: dict = {pid: [] for pid in ids}
    for b in Bed.objects.filter(room__property_id__in=ids).select_related('room').order_by('room__number', 'label'):
        beds[b.room.property_id].append(b)
    taken = set(Booking.objects.filter(bed__room__property_id__in=ids, status__in=BLOCKING, stay_period__overlap=(lo, hi))
                .values_list('bed_id', flat=True))
    ratings = dict(revealed(Rating.objects.filter(booking__bed__room__property_id__in=ids, direction='tenant_to_pg'))
                   .values_list('booking__bed__room__property_id').annotate(a=Avg('score')))
    stays = dict(Booking.objects.filter(bed__room__property_id__in=ids, status__in=['confirmed', 'active', 'ended'])
                 .values_list('bed__room__property_id').annotate(n=Count('id')))
    rooms: dict = {pid: [] for pid in ids}
    for r in Room.objects.filter(property_id__in=ids).order_by('number'):
        rooms[r.property_id].append(r)
    from .models import Photo
    photos: dict = {pid: [] for pid in ids}
    for ph in Photo.objects.filter(property_id__in=ids, ticket__isnull=True, status='live').select_related('room'):
        photos[ph.property_id].append({'id': str(ph.id), 'url': ph.image.url, 'thumb': ph.thumb.url if ph.thumb else ph.image.url,
                                       'room': ph.room.number if ph.room else None, 'caption': ph.caption, 'taken_at': ph.taken_at})
    live = Application.objects.filter(property_id__in=ids, status__in=['forming', 'pending'])
    stats = {r['room_id']: r for r in live.filter(amount_paise__isnull=False).values('room_id')
             .annotate(n=Count('id'), lo=Min('amount_paise'), hi=Max('amount_paise'))}
    now = timezone.now()
    since = now - timedelta(days=14)
    bidders = dict(live.values_list('property_id').annotate(n=Count('lead', distinct=True)))
    visitors = dict(Visit.objects.filter(property_id__in=ids, created_at__gte=since).values_list('property_id')
                    .annotate(n=Count('tenant', distinct=True)))
    out = []
    for p in props:
        free = [bd for bd in beds[p.id] if bd.id not in taken]
        first = free[0] if free else None
        rent = first.room.rent_paise if first else min((bd.room.rent_paise for bd in beds[p.id]), default=0)
        room_cards = []
        for r in rooms[p.id]:
            n_free = sum(1 for bd in free if bd.room_id == r.id)
            st = stats.get(r.id)
            # past its Friday deadline a room up for bids takes no more bids, and no listed-rent requests either, until
            # the owner picks a bid or stops: it isn't offered to tenants in the meantime
            choosing = bool(r.offers_open and r.offers_close_at and r.offers_close_at < now)
            room_cards.append({'_choosing': choosing, 'number': r.number, 'kind': r.kind, 'kind_label': r.get_kind_display(), 'rent_paise': r.rent_paise,
                               'beds': sum(1 for bd in beds[p.id] if bd.room_id == r.id), 'free': n_free, 'bidding': r.offers_open and not choosing, 'instant': r.instant_book and not r.offers_open,
                               'cap_paise': offer_cap_paise(r.rent_paise), 'closes_at': r.offers_close_at if r.offers_open and not choosing else None,
                               'bids': st['n'] if st else 0, 'min_bid_paise': st['lo'] if st else None, 'max_bid_paise': st['hi'] if st else None})
        lat, lng = float(p.lat or 0), float(p.lng or 0)
        avg = ratings.get(p.id)
        out.append({
            'id': p.slug, 'name': p.name, 'gender': p.gender, 'area': p.area, 'city': p.city,
            'address': p.address, 'meals': p.meals, 'lat': lat, 'lng': lng,
            'rent_paise': rent, 'free': len(free), 'rating': round(float(avg), 1) if avg is not None else None,
            'stays': stays.get(p.id, 0), 'hot': any(c['bidding'] and c['free'] for c in room_cards),
            'watching': bidders.get(p.id, 0) + visitors.get(p.id, 0),
            'free_bed': {'bed_id': first.id, 'room': first.room.number, 'bed': first.label, 'kind': first.room.get_kind_display(),
                         'rent_paise': first.room.rent_paise, 'offers_open': first.room.offers_open} if first else None,
            'rooms': [c for c in room_cards if c['free'] and not c['_choosing']],
            'photos': photos[p.id],
            'deposit_months': p.deposit_months, 'notice_months': p.notice_months, 'tariff_paise': p.tariff_paise,
            'verified_owner': p.organisation.verified_at is not None, 'move_in_on': start,
            # false while the trust team checks it (new, or a verified detail changed) or the owner has paused it
            'taking_tenants': p.status == 'published',
            'km': round(km_between(near[0], near[1], lat, lng), 1) if near else None,
        })
    return out


def listing(prop: Property, near: tuple[float, float] | None = None) -> dict:
    return listings([prop], near)[0]


def search(lat: float | None, lng: float | None, radius_km: float, gender: str | None, q: str | None, *,
           bbox: tuple[float, float, float, float] | None = None, max_rent_paise: int | None = None,
           kind: str | None = None, free_only: bool = False, limit: int = 100) -> list[dict]:
    """Published PGs inside a box (west, south, east, north) or within `radius_km` of a point, then filtered and sorted.
    A point alongside a box is only the reference for each card's distance and the sort. Room and bed filters read the
    cards `listings()` already built, so the number of queries does not depend on how many PGs match."""
    with system():
        qs = Property.objects.filter(status='published').select_related('organisation')
        if gender:
            qs = qs.filter(gender=gender)
        if q:
            for word in q.split():
                qs = qs.filter(Q(name__icontains=word) | Q(area__icontains=word) | Q(gender__icontains=word) | Q(city__icontains=word))
        near = (lat, lng) if lat is not None and lng is not None else None
        if bbox:
            west, south, east, north = (Decimal(str(v)) for v in bbox)
            qs = qs.filter(lat__range=(south, north), lng__range=(west, east))
        elif near:  # cheap bounding box before the exact distance
            dlat = Decimal(radius_km / 110.574)
            dlng = Decimal(radius_km / (111.32 * math.cos(lat * math.pi / 180)))
            qs = qs.filter(lat__range=(Decimal(lat) - dlat, Decimal(lat) + dlat), lng__range=(Decimal(lng) - dlng, Decimal(lng) + dlng))
        out = listings(list(qs), near)
    if near and not bbox:
        out = [x for x in out if x['km'] <= radius_km]
    if max_rent_paise is not None or kind:
        kept = []
        for x in out:  # `rooms` holds only rooms with a free bed, so a match is always a bed the tenant can get
            fits = [r['rent_paise'] for r in x['rooms']
                    if (max_rent_paise is None or r['rent_paise'] <= max_rent_paise) and (not kind or r['kind'] == kind)]
            if fits:
                x['rent_paise'] = min(fits)
                kept.append(x)
        out = kept
    elif free_only:
        out = [x for x in out if x['free'] > 0]
    if near:
        for x in out:
            x['km'] = max(0.1, x['km'])
        out.sort(key=lambda x: x['km'])
    else:
        out.sort(key=lambda x: (x['free'] == 0, x['rent_paise'], x['name']))
    return out[:limit]


# ---- places ---------------------------------------------------------------------------------------------

_SECTOR = re.compile(r'\b(?:sector|sec)\s*(\d)')
_PHASE = re.compile(r'\b(?:phase|ph)\s*(\d)')


def normalise_place_query(q: str) -> str:
    """How people type places: `sec 22`, `sector22`, `ph 7` become `sector 22`, `phase 7`."""
    q = ' '.join(q.lower().split())
    return _PHASE.sub(r'phase \1', _SECTOR.sub(r'sector \1', q))


def places(q: str | None, limit: int = 8) -> list[Place]:
    """Places matching what was typed: every word must be in the name or aliases. Names that start with the query come
    before names that merely contain it, then ranked (popular) places by rank, then name. Digits alone mean a sector. Without a
    query, the ranked places in order."""
    qs = Place.objects.all()
    q = ' '.join((q or '').split()[:6])[:60]
    if not q:
        return list(qs.filter(popular_rank__isnull=False).order_by('popular_rank')[:limit])
    norm = normalise_place_query(q)
    digits_only = norm.isdigit()
    words = [norm] if digits_only else norm.split()
    for w in words:
        if w.isdigit():  # `22` is a whole number, not the start of `220`
            rx = rf'(^|[^0-9]){w}($|[^0-9])'
            qs = qs.filter(Q(name__iregex=rx) | Q(aliases__iregex=rx))
        else:
            qs = qs.filter(Q(name__icontains=w) | Q(aliases__icontains=w))
    full = f'sector {norm}' if digits_only else norm
    rank = Case(When(name__iexact=full, then=0), When(Q(name__istartswith=full) | Q(name__istartswith=q), then=1), default=2,
                output_field=IntegerField())
    return list(qs.annotate(rank=rank).order_by('rank', F('popular_rank').asc(nulls_last=True), 'name')[:limit])


def by_slug(slug: str) -> dict | None:
    with system():
        p = Property.objects.filter(slug=slug).exclude(status='draft').select_related('organisation').first()
        return listing(p) if p else None
