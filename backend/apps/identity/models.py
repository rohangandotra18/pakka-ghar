"""Sign-in: one-time codes by SMS or WhatsApp, and revocable session tokens."""
from django.db import models

from apps.core.models import Party, UUIDModel


class OtpChallenge(UUIDModel):
    phone = models.CharField(max_length=16)
    ip = models.GenericIPAddressField(null=True, blank=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.SmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # the per-phone and per-network limits count recent codes on every request, hardest when someone is spamming
        indexes = [models.Index(fields=['phone', 'created_at']), models.Index(fields=['ip', 'created_at'])]


class SessionToken(UUIDModel):
    """Only the SHA-256 of the token is stored. Revoking one denies access at once."""
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name='tokens')
    token_hash = models.CharField(max_length=64, unique=True)
    device = models.CharField(max_length=80, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
