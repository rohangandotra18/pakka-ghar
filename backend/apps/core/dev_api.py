"""Development stand-ins, mounted at /api/dev only when DEBUG is on. Until a payment partner is connected, this
plays the partner's part: it sends the same signed webhook the partner would, through the real handler."""
from uuid import UUID

from ninja import Router

from apps.booking.api import PaymentOut, payment_out
from apps.payments import services as pay
from apps.payments.models import Payment

from .api_support import ApiError, party_of

router = Router(tags=['dev'])


@router.post('/payments/{payment_id}/capture', response=PaymentOut, summary='Act as the payment partner: capture this payment')
def capture(request, payment_id: UUID, method: str = 'upi'):
    p = Payment.objects.filter(pk=payment_id, party=party_of(request)).first()
    if not p:
        raise ApiError(404, 'not_found', 'No such payment.')
    pay.simulate_capture(p, method)
    p.refresh_from_db()
    return payment_out(p)
