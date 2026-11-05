"""The payment partner's webhook. It is the only way a payment becomes captured."""
from django.http import HttpResponse
from ninja import Router

from . import services

router = Router(tags=['webhooks'])


@router.post('/webhooks/razorpay', auth=None, summary='Razorpay events, checked by HMAC signature and stored once')
def razorpay(request):
    result = services.handle_webhook(request.body, request.headers.get('X-Razorpay-Signature', ''),
                                     request.headers.get('X-Razorpay-Event-Id', ''))
    return HttpResponse(result, content_type='text/plain')
