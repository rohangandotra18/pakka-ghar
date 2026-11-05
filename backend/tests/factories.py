"""Builders for test records. They write through the real models, ledger and constraints, with the system role
around them supplied by the caller."""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.booking.models import Agreement, Booking, PoliceVerification, Rating
from apps.core.api_support import add_months, ist, month_start, today
from apps.core.ledger import post
from apps.core.models import Membership, Organisation, Party
from apps.payments.models import Payment
from apps.property.models import Bed, Meter, MeterReading, OwnershipDocument, PayoutAccount, Property, Room

R = random.Random(42)
FIRST = ['Aarav', 'Kabir', 'Rehan', 'Manav', 'Tanish', 'Parth', 'Dhruv', 'Kunal', 'Mohit', 'Siddharth', 'Vansh', 'Rajat',
         'Aditya', 'Pranav', 'Jaskaran', 'Gurpreet', 'Navdeep', 'Harman', 'Ankit', 'Sumit', 'Tarun', 'Nitin', 'Lakshya', 'Ritesh']
GIRLS = ['Ananya', 'Ishita', 'Kritika', 'Navneet', 'Simranjeet', 'Mehak', 'Tanvi', 'Riya', 'Pooja', 'Harleen', 'Sakshi',
         'Jasleen', 'Diya', 'Aastha', 'Prerna', 'Muskan', 'Avneet', 'Khushi', 'Nandini', 'Gurleen']
LAST = ['Sharma', 'Verma', 'Gill', 'Sandhu', 'Bansal', 'Chauhan', 'Kapoor', 'Malhotra', 'Rana', 'Thakur', 'Garg', 'Arora',
        'Bhatia', 'Mehta', 'Saini', 'Dhillon', 'Goyal', 'Jindal', 'Sood', 'Bajwa']
_phone = [9000000000]


WORK = ['Panjab University', 'PGIMER', 'Chandigarh University', 'Infosys, IT Park', 'Quark City', 'DAV College', 'Tech Mahindra, IT Park']


def person(name: str, phone: str | None = None, verified: bool = True, **kw) -> Party:
    kw.setdefault('works_at', R.choice(WORK))
    if not phone:
        _phone[0] += 1
        phone = f'+91{_phone[0]}'
    p = Party.objects.create(phone=phone, name=name, **kw)
    if verified:
        p.aadhaar_masked = f'XXXXXXXX{R.randint(1000, 9999)}'
        p.digilocker_ref = f'DL-seed{R.randint(10**5, 10**6)}'
        p.kyc_verified_at = p.selfie_matched_at = timezone.now() - timedelta(days=R.randint(30, 400))
        p.profile = {'guardian_name': f'{R.choice(FIRST)} {name.split()[-1]}', 'date_of_birth': f'200{R.randint(0, 6)}-0{R.randint(1, 9)}-1{R.randint(0, 9)}',
                     'home_address': f'{R.randint(1, 900)}, Model Town, Ludhiana', 'emergency_contact': f'+9198{R.randint(10**7, 10**8 - 1)}'}
        p.save()
    return p


def org_with_owner(name: str, owner: Party, verified: bool = True) -> Organisation:
    o = Organisation.objects.create(name=name, verified_at=timezone.now() - timedelta(days=200) if verified else None,
                                    no_cash_pledged_at=timezone.now() - timedelta(days=200), pan_masked='XXXXX1234X')
    Membership.objects.create(party=owner, organisation=o, role='owner')
    return o


def make_property(org, slug, name, gender, area, address, city, lat, lng, meals, rooms, status='published') -> Property:
    p = Property.objects.create(organisation=org, slug=slug, name=name, gender=gender, area=area, address=address, city=city,
                                lat=Decimal(str(lat)), lng=Decimal(str(lng)), meals=meals, status=status,
                                published_at=timezone.now() - timedelta(days=300) if status == 'published' else None)
    for number, kind, rupees in rooms:
        room = Room.objects.create(organisation=org, property=p, number=number, kind=kind, rent_paise=rupees * 100)
        for i in range({'single': 1, 'double': 2, 'triple': 3}[kind]):
            Bed.objects.create(organisation=org, room=room, label=i + 1)
    for kind in ('sale_deed', 'property_tax'):
        OwnershipDocument.objects.create(organisation=org, property=p, kind=kind, status='accepted', file_name=f'{kind}.pdf')
    OwnershipDocument.objects.create(organisation=org, property=p, kind='pg_registration', status='later')
    PayoutAccount.objects.create(organisation=org, bank_name='HDFC Bank', account_masked='XXXX XXXX 4417', ifsc='HDFC0000123',
                                 name_matched_at=timezone.now() - timedelta(days=200))
    return p


def bed(p: Property, room: str, label: int) -> Bed:
    return Bed.objects.get(room__property=p, room__number=room, label=label)


def stay(b: Bed, guest: Party, start: date, *, months=11, end: date | None = None, status='active', rent=None,
         police='verified', autopay=False, notice_on: date | None = None, deposit_outcome='') -> Booking:
    rent = rent or b.room.rent_paise
    hi = end or max(add_months(start, months), add_months(today(), 6))
    bk = Booking.objects.create(organisation=b.organisation, reference=f'PG-{R.randint(16**7, 16**8 - 1):08X}', bed=b, guest=guest,
                                status=status, stay_period=(ist(start), ist(hi)), months=months, rent_paise=rent,
                                deposit_paise=b.room.rent_paise, autopay=autopay, notice_given_on=notice_on,
                                ended_on=end if status == 'ended' else None, deposit_outcome=deposit_outcome,
                                idempotency_key=f'seed-{R.getrandbits(64):x}', request_fingerprint='seed')
    bk.refresh_from_db()  # stay_period comes back as a DateTimeTZRange
    t = ist(start) - timedelta(days=3)
    Agreement.objects.create(organisation=b.organisation, booking=bk, tenant=guest, tenant_signed_at=t, owner_signed_at=t,
                             stamped_at=t, stamp_certificate=f'IN-CH{R.getrandbits(40):010X}', esign_ref='ESIGN-SEED')
    pv = PoliceVerification.objects.create(organisation=b.organisation, booking=bk, tenant=guest, jurisdiction=b.room.property.city,
                                           status=police, submitted_at=t if police != 'not_started' else None,
                                           verified_at=t + timedelta(days=9) if police == 'verified' else None)
    if police != 'verified':
        from apps.booking.police.services import prepare_police
        prepare_police(bk)
    # the deposit, captured into escrow (and settled back out for stays that ended)
    dep = Payment.objects.create(organisation=b.organisation, party=guest, purpose='deposit', booking=bk, amount_paise=bk.deposit_paise,
                                 method='upi', status='captured', provider='fake', provider_order_id=f'order_seed{R.getrandbits(48):x}',
                                 captured_at=t)
    dep.journal = post(b.organisation, 'deposit_captured', f'Deposit · {bk.reference}',
                       [('escrow', None, bk.deposit_paise), ('deposit_liability', guest, -bk.deposit_paise)], ref=dep.provider_order_id)
    dep.save(update_fields=['journal'])
    if status == 'ended':
        kept = 200000 if 'kept' in deposit_outcome else 0
        post(b.organisation, 'deposit_settled', f'Deposit settled for {bk.reference}',
             [('deposit_liability', guest, bk.deposit_paise), ('escrow', None, -bk.deposit_paise), ('bank', None, kept), ('deductions_income', None, -kept)])
    pv.refresh_from_db()
    return bk


def rate(bk: Booking, score: float, owner_score: float | None = None, days_ago: int = 30):
    aspects = {a: max(1, min(5, round(score + R.uniform(-0.4, 0.4)))) for a in ('Cleanliness', 'Food', 'Owner response', 'Value')}
    r = Rating.objects.create(organisation=bk.organisation, booking=bk, tenant=bk.guest, direction='tenant_to_pg', aspects=aspects,
                              score=Decimal(str(score)), deposit_on_time=True)
    when = timezone.now() - timedelta(days=days_ago)
    Rating.objects.filter(pk=r.pk).update(created_at=when)
    if owner_score:
        o = Rating.objects.create(organisation=bk.organisation, booking=bk, tenant=bk.guest, direction='owner_to_tenant',
                                  score=Decimal(str(owner_score)), aspects={})
        Rating.objects.filter(pk=o.pk).update(created_at=when)


def meter(room: Room, last_month_units: float, daily: float):
    """A reading at midnight every day from the start of last month to today. Last month adds up to exactly
    `last_month_units`; this month runs at about `daily` units a day."""
    m = Meter.objects.create(organisation=room.organisation, room=room, device_id=f'QUBE-{room.property.slug[:4].upper()}{room.number}')
    prev, cur = month_start(add_months(today(), -1)), month_start(today())
    weights = [R.uniform(0.7, 1.3) for _ in range((cur - prev).days)]
    base, total, d = Decimal('1000.000'), Decimal('1000.000'), prev
    rows = [MeterReading(organisation=room.organisation, meter=m, read_at=ist(d), kwh_total=total)]
    for i, w in enumerate(weights):
        d += timedelta(days=1)
        total = base + Decimal(str(last_month_units)) * Decimal(sum(weights[:i + 1]) / sum(weights)).quantize(Decimal('0.001'))
        rows.append(MeterReading(organisation=room.organisation, meter=m, read_at=ist(d), kwh_total=total.quantize(Decimal('0.001'))))
    while d < today():
        d += timedelta(days=1)
        total += Decimal(str(round(daily * R.uniform(0.7, 1.3), 3)))
        rows.append(MeterReading(organisation=room.organisation, meter=m, read_at=ist(d), kwh_total=total))
    MeterReading.objects.bulk_create(rows)
    return m


