"""Offers, bookings, agreements, visits, police verification and ratings."""
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import BigIntegerRangeField, DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q, Value

from apps.core.models import OrgModel, Party
from apps.property.models import Bed, Property

BLOCKING = ['hold', 'confirmed', 'active']  # statuses that occupy a bed


class Offer(OrgModel):
    """A sealed offer on a scarce bed: between the listed rent and 15% over it. Nothing is charged unless accepted."""
    STATUSES = [('placed', 'Placed'), ('withdrawn', 'Withdrawn'), ('accepted', 'Accepted'), ('declined', 'Declined')]
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name='offers')
    tenant = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='offers')
    amount_paise = models.BigIntegerField()
    months = models.SmallIntegerField()
    move_in_on = models.DateField()
    status = models.CharField(max_length=12, choices=STATUSES, default='placed')
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['bed', 'tenant'], condition=Q(status='placed'), name='one_live_offer_per_bed'),
            models.CheckConstraint(condition=Q(months__in=[6, 9, 11]), name='offer_months_allowed'),
        ]


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
    offer = models.OneToOneField(Offer, null=True, blank=True, on_delete=models.PROTECT, related_name='booking')
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


class Agreement(OrgModel):
    """The PG accommodation agreement: Aadhaar eSign by both sides, then e-stamped."""
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='agreement')
    tenant = models.ForeignKey(Party, on_delete=models.PROTECT)
    terms = models.JSONField(default=dict)
    tenant_signed_at = models.DateTimeField(null=True, blank=True)
    owner_signed_at = models.DateTimeField(null=True, blank=True)
    stamped_at = models.DateTimeField(null=True, blank=True)
    stamp_duty_paise = models.IntegerField(default=10000)
    stamp_certificate = models.CharField(max_length=64, blank=True)
    esign_ref = models.CharField(max_length=64, blank=True)


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
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='visits')
    tenant = models.ForeignKey(Party, on_delete=models.CASCADE)
    slot = models.DateTimeField()
    status = models.CharField(max_length=12, default='requested')  # requested | confirmed | cancelled


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
