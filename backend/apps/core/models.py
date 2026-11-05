"""Core records shared by every module: organisations, people, the append-only ledger, audit trail,
idempotency records and notifications."""
import uuid

from django.db import models
from django.db.models import Q


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Organisation(UUIDModel):
    """Who a business record belongs to: an owner's PG business, or the platform itself."""
    KINDS = [('owner', 'Owner'), ('platform', 'Platform')]
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=KINDS, default='owner')
    gstin = models.CharField(max_length=15, blank=True)          # only if the owner is GST-registered
    pan_masked = models.CharField(max_length=10, blank=True)      # e.g. XXXXX1234X
    verified_at = models.DateTimeField(null=True, blank=True)     # papers checked by the trust team
    no_cash_pledged_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class Party(UUIDModel):
    """A person: tenant, owner or both. Government ID numbers are never stored in full."""
    phone = models.CharField(max_length=16, unique=True)          # E.164, +91XXXXXXXXXX
    name = models.CharField(max_length=120, blank=True)
    works_at = models.CharField(max_length=160, blank=True)
    looking_for = models.CharField(max_length=16, blank=True)     # Boys | Girls | Co-ed
    move_in_on = models.DateField(null=True, blank=True)
    # Zero-disclosure ID: last four digits only, the DigiLocker transaction reference and when it was checked.
    aadhaar_masked = models.CharField(max_length=12, blank=True)  # XXXXXXXX1234
    digilocker_ref = models.CharField(max_length=128, blank=True)
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    selfie_matched_at = models.DateTimeField(null=True, blank=True)
    # What the police tenant-verification form asks for: guardian_name, date_of_birth, home_address,
    # emergency_contact. Shared only with the owner the person books with.
    profile = models.JSONField(default=dict, blank=True)

    @property
    def verified(self) -> bool:
        return self.kyc_verified_at is not None

    @property
    def first_name(self) -> str:
        return (self.name or 'Resident').split(' ')[0]

    def __str__(self):
        return self.name or self.phone


class Membership(UUIDModel):
    ROLES = [('owner', 'Owner'), ('manager', 'Manager'), ('staff', 'Staff')]
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name='memberships')
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=16, choices=ROLES, default='owner')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['party', 'organisation'], name='uniq_membership')]


class OrgModel(UUIDModel):
    """A business record. Row-level security filters these by app.current_org (see apps.core.rls)."""
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditEvent(models.Model):
    """Append-only trail of every change to listings, applications, bookings and money. Never updated."""
    id = models.BigAutoField(primary_key=True)
    organisation = models.ForeignKey(Organisation, null=True, on_delete=models.CASCADE)
    actor = models.ForeignKey(Party, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64)
    entity = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['entity', 'entity_id'])]


class IdempotencyRecord(models.Model):
    """A replayable response for a POST that moves money or holds a bed."""
    id = models.BigAutoField(primary_key=True)
    organisation = models.ForeignKey(Organisation, null=True, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    key = models.CharField(max_length=128)
    fingerprint = models.CharField(max_length=64)
    status = models.SmallIntegerField()
    body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['party', 'key'], name='uniq_idempotency_key')]


class Notification(models.Model):
    """What a person is told in the app; streamed live over server-sent events."""
    id = models.BigAutoField(primary_key=True)
    organisation = models.ForeignKey(Organisation, null=True, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=48)
    title = models.CharField(max_length=200)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)


# ---- Append-only double-entry ledger (amounts in integer paise) -------------------------------------

class Account(OrgModel):
    """One account per organisation, purpose and (for per-person accounts) party."""
    CODES = [
        ('receivable', 'Owed by resident'),
        ('rent_income', 'Rent income'),
        ('electricity_income', 'Electricity recovered'),
        ('deductions_income', 'Deposit deductions'),
        ('deposit_liability', 'Deposit owed back to resident'),
        ('escrow', 'Deposits held by the escrow partner'),
        ('gateway_clearing', 'Collected by the payment partner, not yet settled'),
        ('bank', "Owner's bank account"),
        ('gst_payable', 'GST collected, payable to the government'),
    ]
    code = models.CharField(max_length=32, choices=CODES)
    party = models.ForeignKey(Party, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organisation', 'code', 'party'], name='uniq_account'),
            models.UniqueConstraint(fields=['organisation', 'code'], condition=Q(party__isnull=True), name='uniq_account_orgwide'),
        ]


class Journal(OrgModel):
    """One financial event. Its lines always sum to zero; a reversal is a new journal, never an edit."""
    memo = models.CharField(max_length=200)
    kind = models.CharField(max_length=32)            # rent_charged, payment_captured, deposit_captured, ...
    ref = models.CharField(max_length=64, blank=True)  # the invoice, payment or booking it came from
    reverses = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversed_by')


class LedgerLine(models.Model):
    id = models.BigAutoField(primary_key=True)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='lines')
    party = models.ForeignKey(Party, null=True, on_delete=models.PROTECT)  # copied from the account for RLS
    amount_paise = models.BigIntegerField()  # debit positive, credit negative
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(amount_paise=0), name='ledger_line_nonzero')]
        indexes = [models.Index(fields=['account'])]
