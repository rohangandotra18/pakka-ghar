"""Maintenance requests from residents, and trust reports that go to Pakka Ghar instead of the owner."""
import builtins

from django.db import models

from apps.core.models import OrgModel, Organisation, Party, UUIDModel
from apps.property.models import Property, Room

CATEGORIES = ['Electrical', 'Plumbing', 'Wi-Fi', 'Cleaning', 'Furniture']


class Ticket(OrgModel):
    STATUSES = [('Raised', 'Raised'), ('Assigned', 'Assigned'), ('Fixed', 'Fixed'), ('Confirmed', 'Confirmed')]
    number = models.IntegerField()
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='tickets')
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.SET_NULL)
    raised_by = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='tickets')
    category = models.CharField(max_length=24)
    text = models.TextField()
    status = models.CharField(max_length=10, choices=STATUSES, default='Raised')
    assignee = models.CharField(max_length=80, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    fixed_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['organisation', 'number'], name='uniq_ticket_number')]

    @builtins.property  # the `property` field shadows the builtin in this class body
    def reference(self) -> str:
        return f'R-{self.number}'


class TrustReport(UUIDModel):
    """A wrong listing, or a request to pay cash. Only the reporter and the trust team can see it:
    the owner it is about never can (row-level security has no organisation clause for this table)."""
    CATEGORIES = [('Listing issue', 'Listing issue'), ('Asked to pay in cash', 'Asked to pay in cash')]
    reporter = models.ForeignKey(Party, on_delete=models.PROTECT, related_name='reports')
    organisation = models.ForeignKey(Organisation, null=True, blank=True, on_delete=models.SET_NULL)
    property = models.ForeignKey(Property, null=True, blank=True, on_delete=models.SET_NULL)
    category = models.CharField(max_length=24, choices=CATEGORIES)
    text = models.TextField()
    status = models.CharField(max_length=12, default='open')  # open | confirmed | dismissed
    updated_at = models.DateTimeField(auto_now=True)
