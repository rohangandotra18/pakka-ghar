"""Listings as tenants see them. Availability and ratings span everyone's bookings, so the aggregates are read
with the system role and only public fields leave this module."""
import math
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Q
from django.utils import timezone

from apps.core.api_support import add_months, ist, month_start, today
from apps.core.rls import system

from .models import Bed, Property

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


def free_beds(prop: Property, start=None) -> list[Bed]:
    """Beds with nothing booked for a month from `start` (default: the next move-in date)."""
    from apps.booking.models import BLOCKING
    start = start or next_move_in()
    lo, hi = ist(start), ist(add_months(start, 1))
    beds = Bed.objects.filter(room__property=prop).select_related('room').order_by('-offers_open', 'room__number', 'label')
    return [b for b in beds if not b.bookings.filter(status__in=BLOCKING, stay_period__overlap=(lo, hi)).exists()]


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
    from apps.booking.models import BLOCKING, Booking, Offer, Rating, Visit
    if not props:
        return []
    ids = [p.id for p in props]
    start = next_move_in()
    lo, hi = ist(start), ist(add_months(start, 1))
    beds: dict = {pid: [] for pid in ids}
    for b in Bed.objects.filter(room__property_id__in=ids).select_related('room').order_by('-offers_open', 'room__number', 'label'):
        beds[b.room.property_id].append(b)
    taken = set(Booking.objects.filter(bed__room__property_id__in=ids, status__in=BLOCKING, stay_period__overlap=(lo, hi))
                .values_list('bed_id', flat=True))
    ratings = dict(revealed(Rating.objects.filter(booking__bed__room__property_id__in=ids, direction='tenant_to_pg'))
                   .values_list('booking__bed__room__property_id').annotate(a=Avg('score')))
    stays = dict(Booking.objects.filter(bed__room__property_id__in=ids, status__in=['confirmed', 'active', 'ended'])
                 .values_list('bed__room__property_id').annotate(n=Count('id')))
    hot_beds = [bd.id for pid in ids for bd in beds[pid] if bd.offers_open]
    stats = {r['bed_id']: r for r in Offer.objects.filter(bed_id__in=hot_beds, status='placed').values('bed_id')
             .annotate(n=Count('id'), lo=Min('amount_paise'), hi=Max('amount_paise'))}
    since = timezone.now() - timedelta(days=14)
    bidders = dict(Offer.objects.filter(bed__room__property_id__in=ids, status='placed').values_list('bed__room__property_id')
                   .annotate(n=Count('tenant', distinct=True)))
    visitors = dict(Visit.objects.filter(property_id__in=ids, created_at__gte=since).values_list('property_id')
                    .annotate(n=Count('tenant', distinct=True)))
    out = []
    for p in props:
        free = [bd for bd in beds[p.id] if bd.id not in taken]
        first = free[0] if free else None
        rent = first.room.rent_paise if first else min((bd.room.rent_paise for bd in beds[p.id]), default=0)
        st = stats.get(first.id) if first and first.offers_open else None
        lat, lng = float(p.lat or 0), float(p.lng or 0)
        avg = ratings.get(p.id)
        out.append({
            'id': p.slug, 'name': p.name, 'gender': p.gender, 'area': p.area, 'city': p.city,
            'address': p.address, 'meals': p.meals, 'lat': lat, 'lng': lng,
            'rent_paise': rent, 'free': len(free), 'rating': round(float(avg), 1) if avg is not None else None,
            'stays': stays.get(p.id, 0), 'hot': bool(first and first.offers_open),
            'watching': bidders.get(p.id, 0) + visitors.get(p.id, 0),
            'free_bed': {'bed_id': first.id, 'room': first.room.number, 'bed': first.label, 'kind': first.room.get_kind_display(),
                         'rent_paise': first.room.rent_paise, 'offers_open': first.offers_open} if first else None,
            'offers': {'count': st['n'] if st else 0, 'min_paise': st['lo'] if st else None, 'max_paise': st['hi'] if st else None,
                       'closes_at': first.offers_close_at, 'cap_paise': offer_cap_paise(first.room.rent_paise)}
                      if first and first.offers_open else None,
            'deposit_months': p.deposit_months, 'notice_months': p.notice_months, 'tariff_paise': p.tariff_paise,
            'verified_owner': p.organisation.verified_at is not None, 'move_in_on': start,
            'km': round(km_between(near[0], near[1], lat, lng), 1) if near else None,
        })
    return out


def listing(prop: Property, near: tuple[float, float] | None = None) -> dict:
    return listings([prop], near)[0]


def search(lat: float | None, lng: float | None, radius_km: float, gender: str | None, q: str | None) -> list[dict]:
    with system():
        qs = Property.objects.filter(status='published').select_related('organisation')
        if gender:
            qs = qs.filter(gender=gender)
        if q:
            for word in q.split():
                qs = qs.filter(Q(name__icontains=word) | Q(area__icontains=word) | Q(gender__icontains=word) | Q(city__icontains=word))
        near = (lat, lng) if lat is not None and lng is not None else None
        if near:  # cheap bounding box before the exact distance
            dlat = Decimal(radius_km / 110.574)
            dlng = Decimal(radius_km / (111.32 * math.cos(lat * math.pi / 180)))
            qs = qs.filter(lat__range=(Decimal(lat) - dlat, Decimal(lat) + dlat), lng__range=(Decimal(lng) - dlng, Decimal(lng) + dlng))
        out = listings(list(qs), near)
    if near:
        out = [x for x in out if x['km'] <= radius_km]
        for x in out:
            x['km'] = max(0.1, x['km'])
        out.sort(key=lambda x: x['km'])
    return out


def by_slug(slug: str) -> dict | None:
    with system():
        p = Property.objects.filter(slug=slug).exclude(status='draft').select_related('organisation').first()
        return listing(p) if p else None
