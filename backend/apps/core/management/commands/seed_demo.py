"""Fill an empty local database with believable demo data (development only)."""
import hashlib
import io
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.core.api_support import today
from apps.core.models import Membership, Organisation, Party
from apps.core.rls import system

DEMO_PREFIX = '+9190000'            # every seeded phone number starts like this
STAFF_PHONE, TENANT_PHONES = '+919000000001', ('+919000000002', '+919000000003')

# name, gender, area, address, city, lat, lng, meals, rooms (number, kind, rupees per bed per month),
# beds in use now (room, bed), stays that ended (room, bed, rating)
PUBLISHED = [
    ('Maple Nest Boys PG', 'Boys', 'Sector 15', 'House 1184, Sector 15-C', 'chandigarh', 30.7528, 76.7702, '3 meals',
     [('101', 'double', 9500), ('102', 'triple', 7000), ('103', 'single', 14000)], [('101', 1), ('101', 2), ('102', 1)], [('103', 1, 4.6)]),
    ('Shivalik Girls Residency', 'Girls', 'Sector 11', 'House 612, Sector 11-D', 'chandigarh', 30.7585, 76.7612, '2 meals',
     [('201', 'double', 10500), ('202', 'triple', 8000), ('203', 'single', 15500)], [('201', 1), ('202', 1)], [('202', 2, 4.8), ('201', 2, 4.3)]),
    ('Campus Corner Co-ed PG', 'Co-ed', 'Sector 14', 'House 3, Sector 14 (near Panjab University)', 'chandigarh', 30.7640, 76.7650, 'Breakfast & dinner',
     [('301', 'double', 8500), ('302', 'triple', 6500)], [('301', 1)], [('302', 1, 4.1)]),
    ('Rosewood Girls PG', 'Girls', 'Sector 10', 'House 2047, Sector 10-A', 'chandigarh', 30.7590, 76.7810, '3 meals',
     [('101', 'single', 17500), ('102', 'double', 11500)], [('101', 1)], [('102', 1, 4.9)]),
    ('Scholars Inn Boys PG', 'Boys', 'Sector 16', 'House 905, Sector 16-D', 'chandigarh', 30.7458, 76.7722, 'No meals',
     [('11', 'double', 8000), ('12', 'triple', 6000), ('13', 'triple', 6000)], [('11', 1), ('12', 1)], []),
    ('Lotus Court Girls PG', 'Girls', 'Sector 22', 'Booth 77, Sector 22-A', 'chandigarh', 30.7355, 76.7745, '3 meals',
     [('201', 'double', 11000), ('202', 'single', 16000)], [('201', 1), ('201', 2), ('202', 1)], [('202', 1, 4.5)]),   # completely full
    ('Urban Nest Boys PG', 'Boys', 'Sector 34', 'SCO 118, Sector 34-A', 'chandigarh', 30.7210, 76.7680, '2 meals',
     [('101', 'double', 9000), ('102', 'triple', 7500), ('103', 'single', 13000)], [('102', 1), ('102', 2)], [('101', 1, 4.0)]),
    ('Green Leaf Co-ed PG', 'Co-ed', 'Sector 35', 'House 1531, Sector 35-C', 'chandigarh', 30.7265, 76.7585, '3 meals',
     [('201', 'double', 10000), ('202', 'triple', 7000)], [('201', 1), ('202', 1)], []),
    ('Heritage Girls PG', 'Girls', 'Sector 38', 'House 442, Sector 38-West', 'chandigarh', 30.7338, 76.7490, 'Breakfast & dinner',
     [('101', 'double', 8800), ('102', 'triple', 6800)], [('101', 1)], [('102', 1, 4.4)]),
    ('Phase 3B2 Scholars PG', 'Boys', 'Phase 3B2', 'House 1703, Phase 3B2, Mohali', 'mohali', 30.7135, 76.7165, '2 meals',
     [('101', 'double', 8000), ('102', 'triple', 6200)], [('101', 1), ('102', 1)], [('102', 2, 4.2)]),
    ('Phase 7 Tech Stay', 'Co-ed', 'Phase 7', 'SCO 24, Phase 7, Mohali', 'mohali', 30.7050, 76.7285, '3 meals',
     [('201', 'single', 12500), ('202', 'double', 9500), ('203', 'triple', 7200)], [('202', 1)], [('201', 1, 4.7)]),
    ('Sunrise Girls PG', 'Girls', 'Sector 70', 'House 288, Sector 70, Mohali', 'mohali', 30.6890, 76.7205, '3 meals',
     [('101', 'double', 9200), ('102', 'triple', 7000)], [('101', 1)], []),
    ('Ghaggar View Boys PG', 'Boys', 'Sector 20', 'House 1276, Sector 20, Panchkula', 'panchkula', 30.6930, 76.8540, '2 meals',
     [('101', 'double', 8400), ('102', 'triple', 6500)], [('101', 1), ('102', 1)], [('101', 2, 3.9)]),
    ('Saffron Girls PG', 'Girls', 'Sector 11', 'House 354, Sector 11, Panchkula', 'panchkula', 30.7110, 76.8520, '3 meals',
     [('201', 'double', 9800), ('202', 'single', 14500)], [('201', 1)], [('202', 1, 4.6)]),
]
# waiting for the trust team: the first is complete, the second has no payout account yet
SUBMITTED = [
    ('Banyan Girls PG', 'Girls', 'Sector 19', 'House 731, Sector 19-B', 'chandigarh', 30.7272, 76.7850, '3 meals',
     [('101', 'double', 9300), ('102', 'triple', 7100)], True),
    ('Cedar Boys PG', 'Boys', 'Phase 5', 'House 96, Phase 5, Mohali', 'mohali', 30.7095, 76.7235, '2 meals',
     [('201', 'double', 8200), ('202', 'triple', 6400)], False),
]
OWNERS = ['Harbans Singh Sidhu', 'Kuldeep Kaur', 'Ramesh Chander Bansal', 'Paramjit Singh', 'Sunita Arora', 'Gurmeet Singh Dhillon',
          'Vandana Sood', 'Baldev Raj Goyal', 'Manjit Kaur Gill', 'Anil Kumar Mehta', 'Rajinder Singh Saini', 'Seema Kapoor',
          'Jasbir Singh Bajwa', 'Neelam Malhotra', 'Davinder Thakur', 'Pritam Singh Chauhan']
TINTS = [(214, 232, 220), (226, 218, 238), (240, 226, 206), (206, 226, 240), (238, 214, 218), (222, 236, 206)]


def demo_photo(prop_name: str, n: int, tint) -> tuple[bytes, bytes, tuple[int, int]]:
    """A flat tinted JPEG that says 'Demo photo' and the PG's name: obviously a placeholder."""
    from PIL import Image, ImageDraw, ImageFont
    size = (1200, 800)
    img = Image.new('RGB', size, tint)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, size[0] - 20, size[1] - 20], outline=tuple(int(c * 0.6) for c in tint), width=6)
    dark = tuple(int(c * 0.25) for c in tint)
    d.text((size[0] / 2, 320), 'Demo photo', fill=dark, font=ImageFont.load_default(size=110), anchor='mm')
    d.text((size[0] / 2, 470), prop_name, fill=dark, font=ImageFont.load_default(size=54), anchor='mm')
    d.text((size[0] / 2, 560), f'placeholder {n} of 3', fill=dark, font=ImageFont.load_default(size=36), anchor='mm')
    full = io.BytesIO()
    img.save(full, 'JPEG', quality=80)
    img.thumbnail((480, 480))
    thumb = io.BytesIO()
    img.save(thumb, 'JPEG', quality=75)
    return full.getvalue(), thumb.getvalue(), size


class Command(BaseCommand):
    help = 'Fill an empty local database with demo PGs, owners, residents, reports and placeholder photos (development only).'

    def handle(self, *args, **kw):
        from django.conf import settings
        if not settings.DEBUG:
            self.stderr.write('Refusing: seed_demo is for development only. Run it with DEBUG=1.')
            return
        # development-only: the test builders write through the real models and the ledger
        from tests.factories import FIRST, GIRLS, LAST, R, bed, make_property, org_with_owner, person, rate, stay

        from apps.maintenance.models import TrustReport
        from apps.property.models import Bed, OwnershipDocument, PayoutAccount, Photo, Property, Room

        with system():
            if Property.objects.exists() or Party.objects.filter(phone__startswith=DEMO_PREFIX).exists():
                self.stderr.write('Refusing: the database already has data. Run `manage.py reset_data --yes` first.')
                return

        counts = {'pgs': 0, 'rooms': 0, 'beds': 0, 'residents': 0, 'photos': 0}
        serial = {'owner': 100, 'resident': 200}
        names = {'boys': iter([f'{f} {l}' for l in LAST for f in FIRST]), 'girls': iter([f'{f} {l}' for l in LAST for f in GIRLS])}

        def phone(kind):
            serial[kind] += 1
            return f'+91900000{serial[kind]:04d}'

        def resident(gender, i):
            key = 'girls' if gender == 'Girls' or (gender == 'Co-ed' and i % 2) else 'boys'
            return person(next(names[key]), phone('resident'))

        def photos(prop, owner, n_start):
            for n in range(1, 4):
                full, thumb, (w, h) = demo_photo(prop.name, n, TINTS[(n_start + n) % len(TINTS)])
                ph = Photo(organisation=prop.organisation, property=prop, taken_by=owner, sha256=hashlib.sha256(full).hexdigest(),
                           width=w, height=h, caption='Demo photo', taken_at=timezone.now(), lat=prop.lat, lng=prop.lng,
                           accuracy_m=5, distance_m=0, device='Demo placeholder', status='live')
                ph.image.save('photo.jpg', ContentFile(full), save=False)
                ph.thumb.save('thumb.jpg', ContentFile(thumb), save=False)
                ph.save()
                counts['photos'] += 1

        def build(spec, owner_name, status):
            name, gender, area, address, city, lat, lng, meals, rooms = spec[:9]
            owner = person(owner_name, phone('owner'), works_at='')
            org = org_with_owner(name, owner, verified=status == 'published')
            p = make_property(org, slugify(name), name, gender, area, address, city, lat, lng, meals, rooms, status=status)
            counts['pgs'] += 1
            counts['rooms'] += len(rooms)
            counts['beds'] += Bed.objects.filter(room__property=p).count()
            return owner, org, p

        with transaction.atomic(), system():
            plat, _ = Organisation.objects.get_or_create(kind='platform', defaults={'name': 'Pakka Ghar trust team'})
            staff = Party.objects.create(phone=STAFF_PHONE, name='Trust Team (demo)')
            Membership.objects.get_or_create(party=staff, organisation=plat, defaults={'role': 'staff'})
            tenants = [person(n, ph, works_at='Panjab University') for n, ph in zip(('Demo Tenant One', 'Demo Tenant Two'), TENANT_PHONES)]

            published, first_owner = [], None
            for i, spec in enumerate(PUBLISHED):
                owner, org, p = build(spec, OWNERS[i], 'published')
                first_owner = first_owner or owner
                published.append(p)
                today_ = today()
                for k, (room, label) in enumerate(spec[9]):
                    start = today_ - timedelta(days=R.randint(25, 220))
                    stay(bed(p, room, label), resident(spec[1], i + k), start, months=11)
                    counts['residents'] += 1
                for k, (room, label, score) in enumerate(spec[10]):
                    end = today_ - timedelta(days=R.randint(45, 110))
                    bk = stay(bed(p, room, label), resident(spec[1], i + k + 1), end - timedelta(days=150), months=5, end=end, status='ended')
                    rate(bk, score, owner_score=4.5, days_ago=R.randint(20, 40))
                photos(p, owner, i)

            # one room open for bids, and the instant booking left off: it needs the owner's one-time code as consent
            bid_room = Room.objects.get(property=published[0], number='102')
            bid_room.offers_open, bid_room.offers_close_at = True, timezone.now() + timedelta(days=5)
            bid_room.save(update_fields=['offers_open', 'offers_close_at', 'updated_at'])

            for j, spec in enumerate(SUBMITTED):
                owner, org, p = build(spec, OWNERS[len(PUBLISHED) + j], 'submitted')
                OwnershipDocument.objects.filter(property=p).update(status='uploaded')
                if not spec[9]:
                    PayoutAccount.objects.filter(organisation=org).delete()

            TrustReport.objects.create(reporter=tenants[0], organisation=published[6].organisation, property=published[6],
                                       category='Asked to pay in cash',
                                       text='The owner asked me to pay the first month in cash to keep the bed. (Demo report)')
            TrustReport.objects.create(reporter=tenants[1], organisation=published[1].organisation, property=published[1],
                                       category='Listing issue',
                                       text='The listing says meals are included but the owner says dinner costs extra. (Demo report)')

        out = self.stdout.write
        out(self.style.SUCCESS(f"Demo data ready: {counts['pgs']} PGs ({len(PUBLISHED)} live, {len(SUBMITTED)} waiting for the trust team), "
                               f"{counts['rooms']} rooms, {counts['beds']} beds, {counts['residents']} residents in beds now, "
                               f"{counts['photos']} placeholder photos."))
        out('Sign in with these numbers (with DEBUG=1 the sign-in code is filled in for you):')
        out(f'  Trust team   {STAFF_PHONE}')
        out(f'  Owner        {first_owner.phone}  ({PUBLISHED[0][0]})')
        out(f'  Tenants      {TENANT_PHONES[0]}, {TENANT_PHONES[1]}  (verified, no stay yet)')
