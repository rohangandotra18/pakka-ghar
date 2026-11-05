"""Properties, rooms, beds, electricity meters, ownership papers and payout accounts."""
from django.db import models

from apps.core.models import OrgModel, Organisation

CITIES = [('chandigarh', 'Chandigarh'), ('mohali', 'Mohali'), ('panchkula', 'Panchkula')]
GENDERS = [('Boys', 'Boys'), ('Girls', 'Girls'), ('Co-ed', 'Co-ed')]


class Property(OrgModel):
    STATUSES = [('draft', 'Draft'), ('submitted', 'Submitted for verification'), ('published', 'Published'), ('paused', 'Paused')]
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=160)
    gender = models.CharField(max_length=8, choices=GENDERS)
    address = models.CharField(max_length=240)
    area = models.CharField(max_length=80)                       # e.g. "Sector 15"
    city = models.CharField(max_length=16, choices=CITIES)
    # The exact building the owner pinned; tenants see the listing at this point.
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    meals = models.CharField(max_length=24, default='3 meals')
    status = models.CharField(max_length=16, choices=STATUSES, default='draft')
    published_at = models.DateTimeField(null=True, blank=True)
    deposit_months = models.SmallIntegerField(default=1)
    notice_months = models.SmallIntegerField(default=1)
    tariff_paise = models.IntegerField(default=725)              # per kWh; never above the DISCOM tariff
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'city'])]


class Room(OrgModel):
    KINDS = [('single', 'Single'), ('double', 'Double sharing'), ('triple', 'Triple sharing')]
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='rooms')
    number = models.CharField(max_length=8)
    kind = models.CharField(max_length=8, choices=KINDS)
    rent_paise = models.BigIntegerField()                        # per bed per month

    class Meta:
        constraints = [models.UniqueConstraint(fields=['property', 'number'], name='uniq_room_number')]
        ordering = ['number']


class Bed(models.Model):
    """The bookable space. Its integer id feeds the booking exclusion constraint (see booking.models)."""
    id = models.BigAutoField(primary_key=True)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='beds')
    label = models.SmallIntegerField()                           # bed 1, 2, 3 in the room
    offers_open = models.BooleanField(default=False)            # scarce bed: sealed offers instead of first-come
    offers_close_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['room', 'label'], name='uniq_bed_label')]
        ordering = ['room__number', 'label']


class Meter(OrgModel):
    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name='meter')
    device_id = models.CharField(max_length=64, unique=True)
    model = models.CharField(max_length=40, default='Qube One')
    paired_at = models.DateTimeField(auto_now_add=True)


class MeterReading(models.Model):
    """Cumulative kWh as reported by the meter. Bills use the difference between two readings."""
    id = models.BigAutoField(primary_key=True)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='readings')
    read_at = models.DateTimeField()
    kwh_total = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['meter', 'read_at'], name='uniq_meter_reading')]
        ordering = ['read_at']


class OwnershipDocument(OrgModel):
    KINDS = [('sale_deed', 'Sale deed or allotment letter'), ('property_tax', 'Latest property tax receipt'),
             ('pg_registration', 'PG registration (Estate Office)'), ('lease', 'Lease that allows subletting')]
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='documents')
    kind = models.CharField(max_length=24, choices=KINDS)
    status = models.CharField(max_length=12, default='uploaded')  # uploaded | later | accepted | rejected
    file_name = models.CharField(max_length=200, blank=True)


class PayoutAccount(OrgModel):
    bank_name = models.CharField(max_length=80)
    account_masked = models.CharField(max_length=24)             # XXXX XXXX 4417
    ifsc = models.CharField(max_length=11)
    name_matched_at = models.DateTimeField(null=True, blank=True)  # ₹1 penny-drop check
