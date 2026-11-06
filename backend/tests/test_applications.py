"""Applying to stay, with roommates; rooms up for bids; tours at chosen times; camera-only, on-site photos."""
import io
import uuid
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.booking.models import Booking
from apps.core.rls import system
from apps.property.models import Photo

from .conftest import Api, read
from .factories import person


def _mine(api):
    return api.get('/applications/mine').json()


# ---- roommates ----------------------------------------------------------------------------------------

def test_roommates_join_then_each_gets_a_bed_in_the_same_room(world):
    simran, aman = world['api'](world['simran']), world['api'](world['aman'])
    a = simran.post('/applications', {'listing': 'gurnoor', 'room': '204', 'roommates': ['98765 00001'], 'message': 'Sisters'}).json()
    assert a['status'] == 'forming' and [m['status'] for m in a['members']] == ['joined', 'invited']
    owner = world['api'](world['owner_b'])
    assert owner.get('/owner/applications').json()['applications'] == []          # not shown until everyone has joined
    inv = aman.get('/invites').json()
    assert [i['from_name'] for i in inv] == ['Simran Kaur']
    joined = aman.post(f"/invites/{inv[0]['member_id']}", {'accept': True}).json()
    assert joined['status'] == 'pending'
    q = owner.get('/owner/applications').json()['applications']
    assert q[0]['size'] == 2 and {m['name'] for m in q[0]['members']} == {'Simran Kaur', 'Aman Verma'}
    owner.post(f"/owner/applications/{a['id']}/accept", {})
    holds = read(lambda: list(Booking.objects.filter(application_id=a['id']).values_list('guest__name', 'bed__room__number', 'status')))
    assert sorted(holds) == [('Aman Verma', '204', 'hold'), ('Simran Kaur', '204', 'hold')]
    assert {x['my_booking_id'] is not None for x in _mine(aman)} == {True}        # each sees their own bed to pay for


def test_an_unverified_roommate_must_verify_and_a_no_can_be_replaced(world):
    simran = world['api'](world['simran'])
    a = simran.post('/applications', {'listing': 'gurnoor', 'roommates': ['98765 00002']}).json()
    ishaan = world['api'](world['unverified'])
    inv = ishaan.get('/invites').json()[0]
    assert ishaan.post(f"/invites/{inv['member_id']}", {'accept': True}).json()['code'] == 'verify_identity'
    ishaan.post(f"/invites/{inv['member_id']}", {'accept': False})
    after = simran.get('/applications/mine').json()[0]
    assert after['status'] == 'forming'
    seat = next(m for m in after['members'] if not m['is_lead'])
    assert simran.post(f"/applications/{a['id']}/members/{seat['id']}/remove").json()['status'] == 'pending'


def test_group_needs_enough_beds_together(world):
    r = world['api'](world['simran']).post('/applications', {'listing': 'sidhu', 'room': '101', 'roommates': ['98111 00001', '98111 00002']})
    assert r.status_code == 409 and r.json()['code'] == 'not_enough_beds'        # a double room can't take three
    assert world['api'](world['simran']).post('/applications', {'listing': 'sidhu', 'roommates': ['98765 43210']}).json()['code'] == 'roommate_is_you'


def test_one_live_application_per_pg(world):
    api = world['api'](world['simran'])
    assert api.post('/applications', {'listing': 'sidhu'}).status_code == 200
    assert api.post('/applications', {'listing': 'sidhu', 'room': '104'}).json()['code'] == 'already_applied'


# ---- bidding on a room ----------------------------------------------------------------------------------

def test_bids_are_sealed_capped_and_the_best_wins_the_room(world):
    owner = world['api'](world['owner_a'])
    owner.post('/owner/rooms/101/bidding', {'open': True})
    simran, aman = world['api'](world['simran']), world['api'](world['aman'])
    assert simran.post('/applications', {'listing': 'sidhu', 'room': '101'}).json()['code'] == 'bid_out_of_range'   # bidding needs an amount
    assert simran.post('/applications', {'listing': 'sidhu', 'room': '101', 'amount_paise': 1040000}).status_code == 422  # cap ₹10,350
    lo = simran.post('/applications', {'listing': 'sidhu', 'room': '101', 'amount_paise': 950000}).json()
    hi = aman.post('/applications', {'listing': 'sidhu', 'room': '101', 'amount_paise': 1000000, 'roommates': []}).json()
    me = simran.get('/applications/mine').json()[0]
    assert (me['count'], me['rank'], me['max_paise']) == (2, 2, 1000000) and 'Aman' not in str(me)
    assert simran.patch(f"/applications/{lo['id']}", {'amount_paise': 1030000}).json()['rank'] == 1   # raising a bid
    listing = Api().get('/listings/sidhu').json()
    room = next(r for r in listing['rooms'] if r['number'] == '101')
    assert room['bidding'] and room['bids'] == 2 and listing['hot']
    assert world['api'](world['unverified']).post('/applications', {'listing': 'sidhu', 'room': '104', 'amount_paise': 950000}).status_code in (403, 422)
    q = owner.get('/owner/applications').json()
    assert [a['amount_paise'] for a in q['applications']] == [1030000, 1000000]   # best bid first
    owner.post(f"/owner/applications/{lo['id']}/accept", {})
    b = read(lambda: Booking.objects.get(guest=world['simran']))
    assert b.rent_paise == 1030000 and b.deposit_paise == 900000                   # a bid never raises the deposit
    owner.post(f"/owner/applications/{hi['id']}/accept", {})                       # the other free bed in the double
    assert read(lambda: Booking.objects.filter(bed__room__number='101').count()) == 2
    assert not Api().get('/listings/sidhu').json()['hot']                          # room full: bidding over


def test_listed_rent_application_cant_target_a_bidding_room(world):
    world['api'](world['owner_a']).post('/owner/rooms/104/bidding', {'open': True})
    r = world['api'](world['simran']).post('/applications', {'listing': 'sidhu', 'room': '104'})
    assert r.json()['code'] == 'bid_out_of_range'
    ok = world['api'](world['simran']).post('/applications', {'listing': 'sidhu'}).json()      # any room: the double
    q = world['api'](world['owner_a']).get('/owner/applications').json()['applications']
    assert ok['status'] == 'pending' and q[0]['fits'] == ['101']


def test_declined_application_tells_the_applicant(world):
    a = world['api'](world['simran']).post('/applications', {'listing': 'sidhu'}).json()
    world['api'](world['owner_a']).post(f"/owner/applications/{a['id']}/decline", {'reason': 'Full for December'})
    mine = world['api'](world['simran']).get('/applications/mine').json()[0]
    assert (mine['status'], mine['decline_reason']) == ('declined', 'Full for December')


# ---- tours -----------------------------------------------------------------------------------------------

def test_tour_at_a_chosen_free_time(world):
    owner = world['api'](world['owner_b'])
    owner.put('/owner/tour-hours', {'days': [0, 1, 2, 3, 4, 5, 6], 'start': '09:00', 'end': '20:00', 'minutes': 30})
    slots = Api().get('/listings/gurnoor/tour-slots').json()['slots']
    assert len(slots) > 10
    simran, aman = world['api'](world['simran']), world['api'](world['aman'])
    t = simran.post('/visits', {'listing': 'gurnoor', 'slot': slots[3], 'note': 'With my father'}).json()
    assert t['slot'] == slots[3] and t['note'] == 'With my father'
    assert slots[3] not in Api().get('/listings/gurnoor/tour-slots').json()['slots']   # taken
    assert aman.post('/visits', {'listing': 'gurnoor', 'slot': slots[3]}).json()['code'] == 'slot_taken'
    assert owner.put('/owner/tour-hours', {'days': [0], 'start': '18:00', 'end': '10:00'}).status_code == 422
    # the database holds one live tour per slot even if two requests race past the free-time check
    from django.db import IntegrityError, transaction

    from apps.booking.models import Visit
    with system(), pytest.raises(IntegrityError), transaction.atomic():
        v = Visit.objects.get(pk=t['id'])
        Visit.objects.create(organisation=v.organisation, property=v.property, tenant=world['aman'], slot=v.slot)
    # a cancelled tour can't be confirmed back to life
    simran.post(f"/visits/{t['id']}/cancel", {})
    assert owner.post(f"/owner/visits/{t['id']}/confirm", {}).json()['code'] == 'not_open'
    assert slots[3] in Api().get('/listings/gurnoor/tour-slots').json()['slots']        # and the time is free again


# ---- photos -----------------------------------------------------------------------------------------------

def _jpeg(color=(120, 160, 90), software=None, size=(800, 600)):
    from PIL import Image
    img = Image.new('RGB', size, color)
    exif = Image.Exif()
    exif[0x0110] = 'Pixel 8'
    if software:
        exif[0x0131] = software
    exif[0x8825] = {2: (30.0, 45.0, 15.0)}  # a GPS block that must not survive
    buf = io.BytesIO()
    img.save(buf, 'JPEG', exif=exif)
    return buf.getvalue()


def _upload(world, raw, lat=30.7543, lng=76.7713, ago=timedelta(seconds=20), accuracy=12):
    from .conftest import token_for
    return Api().c.post('/api/owner/photos', {'file': SimpleUploadedFile('p.jpg', raw, 'image/jpeg'), 'taken_at': (timezone.now() - ago).isoformat(),
                        'lat': lat, 'lng': lng, 'accuracy_m': accuracy, 'room': '101', 'device': 'Pixel 8'},
                        HTTP_AUTHORIZATION=f'Bearer {token_for(world["owner_a"])}')


def test_photos_must_be_fresh_on_site_camera_shots(world, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    ok = _upload(world, _jpeg())
    assert ok.status_code == 200, ok.content
    assert _upload(world, _jpeg((1, 2, 3)), lat=30.70, lng=76.70).json()['code'] == 'not_on_site'          # 7 km away
    assert _upload(world, _jpeg((4, 5, 6)), ago=timedelta(hours=3)).json()['code'] == 'not_fresh'           # an old picture
    assert _upload(world, _jpeg((7, 8, 9)), accuracy=900).json()['code'] == 'weak_location'
    assert _upload(world, _jpeg()).json()['code'] == 'duplicate'
    assert _upload(world, _jpeg((9, 9, 9), software='Adobe Firefly')).json()['code'] == 'edited'
    assert _upload(world, _jpeg((9, 8, 7), size=(200, 150))).json()['code'] == 'too_small'
    from PIL import Image
    png = io.BytesIO()
    Image.new('RGB', (800, 600), (3, 3, 3)).save(png, 'PNG')
    assert _upload(world, png.getvalue()).json()['code'] == 'not_a_photo'                                   # a screenshot
    huge = io.BytesIO()
    Image.new('L', (9000, 8000), 0).save(huge, 'JPEG', quality=10)                                          # 72 MP, a small file
    assert len(huge.getvalue()) < 12 * 1024 * 1024 and _upload(world, huge.getvalue()).json()['code'] == 'too_big'
    assert _upload(world, b'not an image').json()['code'] == 'not_a_photo'
    stored = read(lambda: Photo.objects.get())
    from PIL import Image
    with Image.open(stored.image.path) as im:
        assert not im.getexif()                                                      # no camera, GPS or software metadata kept
    assert stored.distance_m < 5 and stored.room.number == '101'
    listing = Api().get('/listings/sidhu').json()
    assert len(listing['photos']) == 1 and listing['photos'][0]['room'] == '101'


def test_tenants_cannot_add_listing_photos(world):
    r = world['api'](world['simran']).c.post('/api/owner/photos', {}, HTTP_AUTHORIZATION='Bearer nope')
    assert r.status_code == 401


__all__ = ['person', 'system', 'uuid']


def test_a_lapsed_hold_shows_on_the_application_and_tells_the_owner(world):
    from apps.booking.bookings.services import expire_holds
    from apps.core.models import Notification
    from .helpers import accepted
    tenant = accepted(world, world['simran'], world['owner_a'])
    a = _mine(tenant)[0]
    assert a['status'] == 'accepted' and a['my_booking_status'] == 'hold'
    with system():
        Booking.objects.filter(pk=a['my_booking_id']).update(hold_expires_at=timezone.now() - timedelta(minutes=1))
    assert expire_holds() == 1
    assert _mine(tenant)[0]['my_booking_status'] == 'expired'      # the app says the hold ran out, not "pay deposit"
    told = read(lambda: list(Notification.objects.filter(party=world['owner_a'], kind='booking.expired').values_list('title', flat=True)))
    assert told and 'free again' in told[0]


def test_closing_an_account_frees_the_group_and_cancels_tours(world):
    """A roommate who said no closes their account: the application goes to the owner instead of waiting for ever.
    A tenant who closes their account has their upcoming tours cancelled, confirmed ones too."""
    simran = world['api'](world['simran'])
    simran.post('/applications', {'listing': 'gurnoor', 'roommates': ['98765 00002']})
    ishaan = world['api'](world['unverified'])
    ishaan.post(f"/invites/{ishaan.get('/invites').json()[0]['member_id']}", {'accept': False})
    assert simran.get('/applications/mine').json()[0]['status'] == 'forming'
    assert ishaan.post('/me/delete', {'confirm': 'DELETE'}).json()['deleted']
    assert simran.get('/applications/mine').json()[0]['status'] == 'pending'
    from apps.booking.models import ApplicationMember
    assert not read(lambda: ApplicationMember.objects.filter(phone=world['unverified'].phone).exists())   # number gone

    owner, aman = world['api'](world['owner_b']), world['api'](world['aman'])
    slot = Api().get('/listings/gurnoor/tour-slots').json()['slots'][0]
    v = aman.post('/visits', {'listing': 'gurnoor', 'slot': slot}).json()
    owner.post(f"/owner/visits/{v['id']}/confirm", {})
    assert aman.post('/me/delete', {'confirm': 'DELETE'}).json()['deleted']
    from apps.booking.models import Visit
    assert read(lambda: Visit.objects.get(pk=v['id']).status) == 'cancelled'
    assert slot in Api().get('/listings/gurnoor/tour-slots').json()['slots']


def test_a_paused_pg_takes_no_new_tenants(world):
    """After a confirmed cash report the PG is paused: no new applications, bids, tours or acceptances."""
    from apps.property.models import Property
    simran = world['api'](world['simran'])
    a = simran.post('/applications', {'listing': 'sidhu'}).json()
    with system():
        Property.objects.filter(slug='sidhu').update(status='paused')
    assert world['api'](world['aman']).post('/applications', {'listing': 'sidhu'}).json()['code'] == 'paused'
    assert Api().get('/listings/sidhu/tour-slots').json()['slots'] == []
    assert world['api'](world['aman']).post('/visits', {'listing': 'sidhu'}).json()['code'] == 'paused'
    assert world['api'](world['owner_a']).post(f"/owner/applications/{a['id']}/accept", {}).json()['code'] == 'paused'
