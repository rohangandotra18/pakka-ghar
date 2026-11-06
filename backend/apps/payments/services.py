"""Money in: invoices, payments through a licensed payment partner, webhooks, metered electricity.

Pakka Ghar never holds money. Rent settles from the payment partner to the owner's bank; deposits sit with the
partner's escrow account. The ledger records the owner's side of each event so balances can be shown and audited.
"""
import hashlib
import hmac
import json
import logging
import secrets
import urllib.request
from base64 import b64encode
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.booking.models import Booking
from apps.core.api_support import ApiError, add_months, audit, fy_label, ist, month_start, notify, today
from apps.core.ledger import post, reverse
from apps.core.rls import system
from apps.property.models import MeterReading, Property, Room

from .models import ElectricityRun, Invoice, InvoiceLine, Payment, WebhookEvent

log = logging.getLogger('pakka')

# GST: residential accommodation in a hostel or PG is exempt up to ₹20,000 per person per month when the stay
# runs at least 90 days. VERIFY WITH A CA before launch, and set the taxable rate for stays above the limit.
GST_EXEMPT_LIMIT_PAISE = 20000_00
GST_MIN_DAYS = 90
GST_TAXABLE_RATE_BP = 1200


def gst_rate_bp(rent_paise: int, months: int) -> int:
    return 0 if rent_paise <= GST_EXEMPT_LIMIT_PAISE and months * 30 >= GST_MIN_DAYS else GST_TAXABLE_RATE_BP


def _tax(amount_paise: int, rate_bp: int) -> int:
    return int((Decimal(amount_paise) * rate_bp / 10000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


# ---- invoices ------------------------------------------------------------------------------------------

def _number(org, d: date) -> str:
    fy = fy_label(d)
    n = Invoice.objects.filter(organisation=org, number__startswith=f'PG/{fy}/').count() + 1
    return f'PG/{fy}/{n:04d}'


def charge_month(b: Booking, period: date) -> Invoice:
    """Issue the month's invoice with the rent line and post it to the ledger. Safe to call twice."""
    period = month_start(period)
    existing = Invoice.objects.filter(booking=b, period=period).first()
    if existing:
        return existing
    org = b.organisation
    for attempt in range(3):
        try:
            with transaction.atomic():
                inv = Invoice.objects.create(organisation=org, party=b.guest, booking=b, number=_number(org, period),
                                             period=period, due_on=period + timedelta(days=4), supplier_gstin=org.gstin)
            break
        except IntegrityError:
            if attempt == 2:
                raise
    rate = gst_rate_bp(b.rent_paise, b.months)
    tax = _tax(b.rent_paise, rate)
    j = post(org, 'rent_charged', f'Rent {period:%b %Y} · {b.reference}',
             [('receivable', b.guest, b.rent_paise + tax), ('rent_income', None, -b.rent_paise), ('gst_payable', None, -tax)] if tax
             else [('receivable', b.guest, b.rent_paise), ('rent_income', None, -b.rent_paise)], ref=inv.number)
    InvoiceLine.objects.create(organisation=org, party=b.guest, invoice=inv, kind='rent', description=f'Rent for {period:%B %Y}',
                               rate_paise=b.rent_paise, amount_paise=b.rent_paise, tax_rate_bp=rate, tax_paise=tax, journal=j)
    return inv


def invoice_paid_paise(inv: Invoice) -> int:
    return sum(p.amount_paise for p in inv.payments.filter(status='captured'))


def invoice_out(inv: Invoice) -> dict:
    lines = list(inv.lines.all())
    total = sum(ln.amount_paise + ln.tax_paise for ln in lines)
    return {'id': str(inv.id), 'number': inv.number, 'period': inv.period, 'due_on': inv.due_on, 'status': inv.status,
            'total_paise': total, 'paid_paise': invoice_paid_paise(inv),
            'lines': [{'kind': ln.kind, 'description': ln.description, 'quantity': float(ln.quantity), 'rate_paise': ln.rate_paise,
                       'amount_paise': ln.amount_paise, 'tax_paise': ln.tax_paise, 'sac': ln.sac} for ln in lines]}


# ---- electricity ---------------------------------------------------------------------------------------

def _reading_at(meter, when) -> Decimal | None:
    r = MeterReading.objects.filter(meter=meter, read_at__lte=when).order_by('-read_at').first()
    return r.kwh_total if r else None


def room_units(room: Room, start: date, end: date) -> Decimal:
    meter = getattr(room, 'meter', None)
    if not meter:
        return Decimal(0)
    a, b = _reading_at(meter, ist(start)), _reading_at(meter, ist(end))
    return (b - a) if a is not None and b is not None and b >= a else Decimal(0)


def electricity_shares(prop: Property, usage_month: date) -> dict:
    """Units used in `usage_month`, split between the room's residents by the days each lived there."""
    start, end = month_start(usage_month), add_months(month_start(usage_month), 1)
    lo, hi = ist(start), ist(end)
    out = {'rooms': {}, 'bookings': {}}
    for room in prop.rooms.all().select_related('meter'):
        units = room_units(room, start, end)
        if not units:
            continue
        out['rooms'][room.number] = units
        stays = Booking.objects.filter(bed__room=room, status__in=['active', 'ended', 'confirmed'], stay_period__overlap=(lo, hi))
        days = {}
        for b in stays:
            s, e = max(b.stay_period.lower, lo), min(b.stay_period.upper or hi, hi)
            days[b.id] = max(0, (e - s).days)
        total = sum(days.values())
        for bid, d in days.items():
            if total and d:
                out['bookings'][bid] = (units * d / total).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return out


def send_electricity(prop: Property, period: date, actor) -> ElectricityRun:
    """Add last month's metered units to this month's invoices. Each charge is one ledger journal."""
    period = month_start(period)
    run, _ = ElectricityRun.objects.get_or_create(property=prop, period=period, defaults={'organisation': prop.organisation})
    if run.sent_at:
        return run
    shares = electricity_shares(prop, add_months(period, -1))
    rate = prop.tariff_paise
    for bid, units in shares['bookings'].items():
        b = Booking.objects.get(pk=bid)
        if b.status not in ('active', 'confirmed'):
            continue
        inv = charge_month(b, period)
        if inv.lines.filter(kind='electricity').exists() or not units:
            continue
        amt = int((units * rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        j = post(prop.organisation, 'electricity_charged', f'Electricity {add_months(period, -1):%b %Y} · {b.reference}',
                 [('receivable', b.guest, amt), ('electricity_income', None, -amt)], ref=inv.number)
        InvoiceLine.objects.create(organisation=prop.organisation, party=b.guest, invoice=inv, kind='electricity',
                                   description=f'Electricity {add_months(period, -1):%B}: {units} units at ₹{rate / 100:.2f}',
                                   sac='996311', quantity=units, rate_paise=rate, amount_paise=amt, journal=j)
        if inv.status == 'paid':  # a bill paid before the meter reading was added is open again for the difference
            inv.status = 'open'
            inv.save(update_fields=['status', 'updated_at'])
        notify(b.guest, 'bill.ready', f'Your {period:%B} bill is ready: rent plus {units} units of electricity.', org=prop.organisation)
    run.sent_at = timezone.now()
    run.save(update_fields=['sent_at', 'updated_at'])
    audit(prop.organisation, actor, 'electricity.send', run)
    return run


# ---- payment partner -------------------------------------------------------------------------------------

class FakeGateway:
    name = 'fake'
    key_id = 'rzp_test_pakkaghar'

    def create_order(self, amount_paise: int, receipt: str) -> str:
        return 'order_' + secrets.token_hex(7)


class RazorpayGateway:  # pragma: no cover - needs live keys
    name = 'razorpay'

    @property
    def key_id(self):
        return settings.RAZORPAY_KEY_ID

    def create_order(self, amount_paise: int, receipt: str) -> str:
        body = json.dumps({'amount': amount_paise, 'currency': 'INR', 'receipt': receipt}).encode()
        auth = b64encode(f'{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}'.encode()).decode()
        req = urllib.request.Request('https://api.razorpay.com/v1/orders', data=body, method='POST',
                                     headers={'Content-Type': 'application/json', 'Authorization': f'Basic {auth}'})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)['id']


def gateway():
    return RazorpayGateway() if settings.PAYMENT_PROVIDER == 'razorpay' else FakeGateway()


def create_payment(b: Booking, purpose: str, invoice: Invoice | None = None, method: str = 'upi') -> Payment:
    if purpose == 'deposit':
        if b.status != 'hold':
            raise ApiError(409, 'not_held', 'This bed is no longer held. Start the booking again.')
        amount = b.deposit_paise
    else:
        if not invoice or invoice.status == 'paid':
            raise ApiError(409, 'nothing_due', 'Nothing is due right now.')
        amount = invoice.total_paise - invoice_paid_paise(invoice)
    open_ = b.payments.filter(purpose=purpose, invoice=invoice, status='created', amount_paise=amount).first()
    if open_:
        return open_
    gw = gateway()
    return Payment.objects.create(organisation=b.organisation, party=b.guest, purpose=purpose, booking=b, invoice=invoice,
                                  amount_paise=amount, method=method, provider=gw.name,
                                  provider_order_id=gw.create_order(amount, b.reference))


METHOD_MAP = {'upi': 'upi', 'card': 'card', 'netbanking': 'netbanking'}


def capture(pay: Payment, provider_payment_id: str, amount_paise: int, method: str) -> Payment:
    """Record a captured payment and its ledger journal. Call with the system role (from the webhook)."""
    pay = Payment.objects.select_for_update(of=('self',)).select_related('booking', 'invoice', 'party').get(pk=pay.pk)
    if pay.status == 'captured':
        return pay
    if amount_paise != pay.amount_paise or method not in METHOD_MAP:
        pay.status = 'failed'
        pay.save(update_fields=['status', 'updated_at'])
        log.warning('payment %s rejected: amount %s method %s', pay.pk, amount_paise, method)
        return pay
    b, org = pay.booking, pay.organisation
    pay.status, pay.captured_at, pay.provider_payment_id = 'captured', timezone.now(), provider_payment_id
    pay.method = 'upi_autopay' if (b.autopay and pay.purpose == 'invoice') else METHOD_MAP[method]
    if pay.purpose == 'deposit':
        pay.journal = post(org, 'deposit_captured', f'Deposit · {b.reference}',
                           [('escrow', None, amount_paise), ('deposit_liability', b.guest, -amount_paise)], ref=pay.provider_order_id)
        pay.save()
        _confirm_after_deposit(b, pay)
    else:
        pay.journal = post(org, 'payment_captured', f'Payment {pay.invoice.number}',
                           [('gateway_clearing', None, amount_paise), ('receivable', b.guest, -amount_paise)], ref=pay.provider_order_id)
        pay.save()
        inv = pay.invoice
        if invoice_paid_paise(inv) >= inv.total_paise:
            inv.status = 'paid'
            inv.save(update_fields=['status', 'updated_at'])
        from apps.booking.common import owners_of
        for o in owners_of(org):
            notify(o, 'rent.paid', f'{b.guest.first_name} paid ₹{amount_paise // 100:,} in the app.', org=org, invoice=str(inv.id))
    notify(b.guest, 'payment.captured', f'Paid ₹{amount_paise // 100:,}. Receipt saved.', org=org, payment=str(pay.id))
    return pay


def _refund_deposit(b: Booking, pay: Payment, why: str, tell: str) -> None:
    reverse(pay.journal, f'Deposit refunded: {why} · {b.reference}')
    Payment.objects.filter(pk=pay.pk).update(status='refunded', updated_at=timezone.now())
    notify(b.guest, 'booking.lost', tell, org=b.organisation)


def _confirm_after_deposit(b: Booking, pay: Payment) -> None:
    # locked, and read fresh: a cancel running at the same moment must not slip in between the check and the update
    b = Booking.objects.select_for_update(of=('self',)).select_related('bed__room', 'guest', 'organisation').get(pk=b.pk)
    if b.status not in ('hold', 'expired'):
        # cancelled (or otherwise closed) while the payment was in flight: the money must not stay in escrow
        _refund_deposit(b, pay, f'booking {b.status} before the payment arrived',
                        'Your deposit arrived after the booking was cancelled, so it is being refunded in full.')
        return
    if b.status == 'hold' or b.status == 'expired':
        try:
            with transaction.atomic():
                Booking.objects.filter(pk=b.pk).update(status='confirmed', hold_expires_at=None, updated_at=timezone.now())
        except IntegrityError:  # the hold lapsed and someone else took the bed: give the money back
            _refund_deposit(b, pay, 'bed taken after hold expired', 'Your hold ran out and the bed was taken. Your deposit is being refunded.')
            return
        from apps.booking.common import owners_of
        for o in owners_of(b.organisation):
            notify(o, 'booking.confirmed', f'{b.guest.first_name} paid the deposit for Room {b.bed.room.number}.', org=b.organisation, booking=str(b.id))


def sign_webhook(raw: bytes) -> str:
    return hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def handle_webhook(raw: bytes, signature: str, event_id: str) -> str:
    if not settings.RAZORPAY_WEBHOOK_SECRET or not hmac.compare_digest(sign_webhook(raw), signature or ''):
        raise ApiError(401, 'bad_signature', 'Signature check failed.')
    data = json.loads(raw)
    with system():
        ev, created = WebhookEvent.objects.get_or_create(event_id=event_id or hashlib.sha256(raw).hexdigest(),
                                                         defaults={'provider': 'razorpay', 'payload': data})
        if not created and ev.processed_at:
            return 'duplicate'
        if data.get('event') == 'payment.captured':
            ent = data['payload']['payment']['entity']
            pay = Payment.objects.filter(provider_order_id=ent['order_id']).first()
            if not pay:
                raise ApiError(404, 'unknown_order', 'No payment for that order.')
            capture(pay, ent['id'], int(ent['amount']), ent.get('method', ''))
        ev.processed_at = timezone.now()
        ev.save(update_fields=['processed_at'])
    return 'ok'


def simulate_capture(pay: Payment, method: str = 'upi') -> str:
    """Development only: send ourselves the webhook the payment partner would send, through the real handler."""
    raw = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
        'id': 'pay_' + secrets.token_hex(7), 'order_id': pay.provider_order_id, 'amount': pay.amount_paise, 'method': method}}}}).encode()
    return handle_webhook(raw, sign_webhook(raw), 'evt_' + secrets.token_hex(8))


def settle_to_bank(org) -> int:
    """The partner's daily settlement: move what it collected to the owner's bank."""
    from apps.core.ledger import balance
    amt = balance(org, 'gateway_clearing')
    if amt > 0:
        post(org, 'settlement', f'Settlement {today():%-d %b}', [('bank', None, amt), ('gateway_clearing', None, -amt)])
    return amt
