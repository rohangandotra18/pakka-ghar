"""Applications (with roommates and bids), bookings, agreements, tours, police verification and ratings."""
import builtins

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import BigIntegerRangeField, DateTimeRangeField, RangeOperators
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import F, Func, Q, Value

from apps.core.models import OrgModel, Party
from apps.property.models import Bed, Property

BLOCKING = ['hold', 'confirmed', 'active']  # statuses that occupy a bed


def private_storage():
    from django.conf import settings
    return FileSystemStorage(location=settings.PRIVATE_ROOT)


class Application(OrgModel):
    """A request to stay at a PG: alone or with roommates, at the listed rent or as a bid on a room that is up for
    bids. The owner accepts or declines; on acceptance every member gets a bed in the same room, held for 24 hours."""
    STATUSES = [('forming', 'Waiting for roommates'), ('pending', 'With the owner'), ('accepted', 'Accepted'),
                ('declined', 'Declined'), ('withdrawn', 'Withdrawn')]
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='applications')
    room = models.ForeignKey('property.Room', null=True, blank=True, on_delete=models.SET_NULL, related_name='applications')
    room_kind = models.CharField(max_length=8, blank=True)    # single | double | triple, when any room of a type will do
    lead = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='applications')
    amount_paise = models.BigIntegerField(null=True, blank=True)  # a bid, per bed per month; empty means the listed rent
    months = models.SmallIntegerField(default=11)
    move_in_on = models.DateField()
    message = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default='pending')
    decided_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['property', 'lead'], condition=Q(status__in=['forming', 'pending']), name='one_live_application'),
            models.CheckConstraint(condition=Q(months__in=[6, 9, 11]), name='application_months_allowed'),
        ]

    @builtins.property
    def is_bid(self) -> bool:
        return self.amount_paise is not None


class ApplicationMember(OrgModel):
    """Someone in an application. The lead joins at once; a roommate is invited by phone and joins from their own app."""
    STATUSES = [('invited', 'Invited'), ('joined', 'Joined'), ('declined', 'Said no'), ('left', 'Left')]
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='members')
    phone = models.CharField(max_length=16)
    party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT, related_name='application_seats')
    is_lead = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUSES, default='invited')
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['application', 'phone'], name='one_seat_per_phone')]
        ordering = ['-is_lead', 'created_at']


class Booking(OrgModel):
    STATUSES = [('hold', 'Held while paying'), ('confirmed', 'Deposit paid'), ('active', 'Living here'),
                ('ended', 'Ended'), ('cancelled', 'Cancelled'), ('expired', 'Hold expired')]
    reference = models.CharField(max_length=64, unique=True)
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name='bookings')
    guest = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='bookings')
    status = models.CharField(max_length=12, choices=STATUSES, default='hold')
    stay_period = DateTimeRangeField()
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    months = models.SmallIntegerField(default=11)
    rent_paise = models.BigIntegerField()
    deposit_paise = models.BigIntegerField()      # one month of the listed rent, even when an offer raised the rent
    application = models.ForeignKey(Application, null=True, blank=True, on_delete=models.PROTECT, related_name='bookings')
    autopay = models.BooleanField(default=False)
    notice_given_on = models.DateField(null=True, blank=True)
    ended_on = models.DateField(null=True, blank=True)
    deposit_outcome = models.CharField(max_length=160, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            # No two bookings that occupy a bed may overlap in time, enforced by Postgres itself.
            # int8range(bed_id, bed_id, '[]') && ... is bed equality expressed as a range, which the built-in
            # GiST range operator class indexes; it needs no btree_gist extension.
            ExclusionConstraint(
                name='exclude_space_double_booking',
                index_type='gist',
                expressions=[
                    (Func(F('bed_id'), F('bed_id'), Value('[]'), function='int8range', output_field=BigIntegerRangeField()), RangeOperators.OVERLAPS),
                    ('stay_period', RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=BLOCKING),
            ),
        ]
        indexes = [models.Index(fields=['organisation', 'status']), models.Index(fields=['guest', 'status'])]


class AgreementTemplate(OrgModel):
    """The owner's own agreement, uploaded as a PDF. Each new booking gets a copy with a filled-in cover page.
    Without one, the standard Pakka Ghar agreement is generated from the booking's terms."""
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='agreement_templates')
    file = models.FileField(storage=private_storage, upload_to='templates/')
    name = models.CharField(max_length=120)
    sha256 = models.CharField(max_length=64)
    pages = models.IntegerField()
    active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='+')


class Agreement(OrgModel):
    """This booking's agreement: read and signed electronically by the resident and the owner, then e-stamped.
    `document` is exactly what both sides read; its SHA-256 is recorded with each signature."""
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='agreement')
    tenant = models.ForeignKey(Party, on_delete=models.PROTECT)
    terms = models.JSONField(default=dict)
    document = models.FileField(storage=private_storage, upload_to='agreements/', blank=True)
    document_sha256 = models.CharField(max_length=64, blank=True)
    pages = models.IntegerField(default=0)
    source = models.CharField(max_length=10, default='standard')   # standard | owner (their uploaded PDF)
    signed_document = models.FileField(storage=private_storage, upload_to='agreements/', blank=True)
    signed_sha256 = models.CharField(max_length=64, blank=True)
    tenant_signed_at = models.DateTimeField(null=True, blank=True)
    owner_signed_at = models.DateTimeField(null=True, blank=True)
    stamped_at = models.DateTimeField(null=True, blank=True)
    stamp_duty_paise = models.IntegerField(default=10000)
    stamp_certificate = models.CharField(max_length=64, blank=True)
    esign_ref = models.CharField(max_length=64, blank=True)


class Signature(OrgModel):
    """One side's electronic signature: who, typed name, when, from where, confirmed by a one-time code to their
    phone, over a document with this exact hash. Append-only."""
    agreement = models.ForeignKey(Agreement, on_delete=models.CASCADE, related_name='signatures')
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='signatures')
    role = models.CharField(max_length=8)                 # tenant | owner
    typed_name = models.CharField(max_length=120)
    document_sha256 = models.CharField(max_length=64)
    pages_read = models.IntegerField()
    otp_challenge = models.UUIDField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    signed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['agreement', 'role'], name='one_signature_per_side')]


class PoliceVerification(OrgModel):
    """The tenant-verification packet for the police station of the property's city."""
    STATUSES = [('not_started', 'Not started'), ('submitted', 'Submitted'), ('verified', 'Verified')]
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='police')
    tenant = models.ForeignKey(Party, on_delete=models.PROTECT)
    jurisdiction = models.CharField(max_length=16)
    status = models.CharField(max_length=12, choices=STATUSES, default='not_started')
    packet = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(Party, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')


class Visit(OrgModel):
    """A tour of the PG at a time the tenant picked from the owner's tour hours."""
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='visits')
    tenant = models.ForeignKey(Party, on_delete=models.CASCADE)
    slot = models.DateTimeField()
    status = models.CharField(max_length=12, default='requested')  # requested | confirmed | declined | cancelled
    note = models.CharField(max_length=200, blank=True)            # from the tenant ("coming with my father")
    decided_at = models.DateTimeField(null=True, blank=True)


class Rating(OrgModel):
    """End-of-stay ratings. Each side's rating stays hidden until both have rated, or 14 days pass."""
    DIRECTIONS = [('tenant_to_pg', 'Resident rates the PG'), ('owner_to_tenant', 'Owner rates the resident')]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='ratings')
    tenant = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='+')
    direction = models.CharField(max_length=16, choices=DIRECTIONS)
    aspects = models.JSONField(default=dict)
    score = models.DecimalField(max_digits=2, decimal_places=1)
    comment = models.TextField(blank=True)
    deposit_on_time = models.BooleanField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['booking', 'direction'], name='one_rating_per_side'),
            models.CheckConstraint(condition=Q(score__gte=1) & Q(score__lte=5), name='rating_score_range'),
        ]
