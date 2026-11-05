"""Invoices, payments through the licensed payment partner, and reminders. There is no cash method."""
from django.db import models

from apps.booking.models import Booking
from apps.core.models import Journal, OrgModel, Organisation, Party
from apps.property.models import Property

METHODS = [('upi', 'UPI'), ('upi_autopay', 'UPI AutoPay'), ('card', 'Card'), ('netbanking', 'Net banking')]


class Invoice(OrgModel):
    """A monthly bill: rent plus metered electricity. Numbered per organisation and financial year."""
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='invoices')
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name='invoices')
    number = models.CharField(max_length=32)
    period = models.DateField()                       # first day of the month billed
    due_on = models.DateField()
    status = models.CharField(max_length=8, default='open')  # open | paid | void
    supplier_gstin = models.CharField(max_length=15, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organisation', 'number'], name='uniq_invoice_number'),
            models.UniqueConstraint(fields=['booking', 'period'], name='one_invoice_per_month'),
        ]

    @property
    def total_paise(self) -> int:
        return sum(ln.amount_paise + ln.tax_paise for ln in self.lines.all())


class InvoiceLine(models.Model):
    id = models.BigAutoField(primary_key=True)
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.PROTECT)  # copied from the invoice for RLS
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    kind = models.CharField(max_length=16)            # rent | electricity
    description = models.CharField(max_length=160)
    sac = models.CharField(max_length=8, default='996311')  # accommodation services
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    rate_paise = models.BigIntegerField()
    amount_paise = models.BigIntegerField()
    tax_rate_bp = models.IntegerField(default=0)       # basis points; 0 when exempt
    tax_paise = models.BigIntegerField(default=0)
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, null=True)


class Payment(OrgModel):
    PURPOSES = [('deposit', 'Deposit'), ('invoice', 'Monthly bill')]
    STATUSES = [('created', 'Created'), ('captured', 'Captured'), ('failed', 'Failed'), ('refunded', 'Refunded')]
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='payments')
    purpose = models.CharField(max_length=8, choices=PURPOSES)
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name='payments')
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.PROTECT, related_name='payments')
    amount_paise = models.BigIntegerField()
    method = models.CharField(max_length=12, choices=METHODS, default='upi')
    status = models.CharField(max_length=10, choices=STATUSES, default='created')
    provider = models.CharField(max_length=16)
    provider_order_id = models.CharField(max_length=64, unique=True)
    provider_payment_id = models.CharField(max_length=64, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    journal = models.ForeignKey(Journal, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(amount_paise__gt=0), name='payment_positive')]


class WebhookEvent(models.Model):
    """Every webhook delivery, stored once by event id so retries are harmless. Readable only by the system role."""
    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=16)
    event_id = models.CharField(max_length=128, unique=True)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)


class Reminder(OrgModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='reminders')
    channel = models.CharField(max_length=24, default='app+whatsapp')


class ElectricityRun(OrgModel):
    """The month's meter bills, added to residents' invoices when the owner sends them."""
    property = models.ForeignKey(Property, on_delete=models.CASCADE)
    period = models.DateField()
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['property', 'period'], name='one_electricity_run')]
