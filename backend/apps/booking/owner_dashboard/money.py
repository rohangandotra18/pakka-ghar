"""Owner API: money in, reminders, and the year statement."""
from datetime import date
from uuid import UUID

from django.db.models import Sum
from django.utils import timezone
from ninja import Router, Schema

from apps.core.api_support import IST, ApiError, add_months, fy_label, month_start, today
from apps.core.ledger import balance
from apps.core.models import LedgerLine
from apps.core.rls import system
from apps.payments import services as pay
from apps.payments.models import ElectricityRun, Invoice, Reminder
from apps.property.models import MeterReading, PayoutAccount

from .. import common
from ..models import Booking

router = Router(tags=['owner'])


# ---- money --------------------------------------------------------------------------------------------------

class MoneyRow(Schema):
    booking_id: UUID
    invoice_id: UUID
    name: str
    room: str
    units: float
    autopay: bool
    due_paise: int
    paid: bool
    reminded: bool


class RoomUnits(Schema):
    room: str
    units: float
    amount_paise: int


class MoneyOut(Schema):
    period: date
    collected_paise: int
    due_paise: int
    rows: list[MoneyRow]
    rooms: list[RoomUnits]
    read_on: date | None
    tariff_paise: int
    bills_sent: bool
    escrow_paise: int
    next_payout_paise: int
    payout_account: str | None


@router.get('/owner/money', response=MoneyOut)
def money(request):
    p = common.owner_property(request)
    period = month_start(today())
    run = ElectricityRun.objects.filter(property=p, period=period).first()
    sent = bool(run and run.sent_at)
    shares = pay.electricity_shares(p, add_months(period, -1))
    rows, due_total, got = [], 0, 0
    for b in common.current_residents(p):
        with system():  # the monthly charge job, run on demand if it hasn't yet
            inv = pay.charge_month(Booking.objects.get(pk=b.pk), period)
        inv = Invoice.objects.prefetch_related('lines').get(pk=inv.pk)
        units = shares['bookings'].get(b.id, 0)
        pending = 0 if sent else int(units * p.tariff_paise)
        due = inv.total_paise + pending
        paid = inv.status == 'paid' and not pending
        due_total += due
        got += pay.invoice_paid_paise(inv)
        rows.append({'booking_id': b.id, 'invoice_id': inv.id, 'name': b.guest.name, 'room': b.bed.room.number, 'units': float(units),
                     'autopay': b.autopay, 'due_paise': due, 'paid': paid,
                     'reminded': Reminder.objects.filter(invoice=inv).exists()})
    meter_read = MeterReading.objects.filter(meter__room__property=p, read_at__lte=timezone.now().replace(day=1)).order_by('-read_at').first()
    acct = PayoutAccount.objects.filter(organisation=p.organisation).order_by('-created_at').first()
    return {'period': period, 'collected_paise': got, 'due_paise': due_total, 'rows': rows,
            'rooms': [{'room': r, 'units': float(u), 'amount_paise': int(u * p.tariff_paise)} for r, u in sorted(shares['rooms'].items())],
            'read_on': meter_read.read_at.astimezone(IST).date() if meter_read else None, 'tariff_paise': p.tariff_paise, 'bills_sent': sent,
            'escrow_paise': balance(p.organisation, 'escrow'), 'next_payout_paise': balance(p.organisation, 'gateway_clearing'),
            'payout_account': f'{acct.bank_name} ••{acct.account_masked[-4:]}' if acct else None}


@router.post('/owner/money/{invoice_id}/remind', response=MoneyOut, summary='Remind in the app and on WhatsApp')
def remind(request, invoice_id: UUID):
    p = common.owner_property(request)
    inv = Invoice.objects.filter(pk=invoice_id, booking__bed__room__property=p).select_related('party').first()
    if not inv:
        raise ApiError(404, 'not_found', 'No such bill.')
    if not Reminder.objects.filter(invoice=inv, created_at__date=today()).exists():
        Reminder.objects.create(organisation=p.organisation, invoice=inv)
        from apps.core.api_support import notify
        notify(inv.party, 'rent.reminder', f'Your {inv.period:%B} bill is due. Pay in the app.', org=p.organisation, invoice=str(inv.id))
    return money(request)


class StatementRow(Schema):
    name: str
    room: str
    rent_paise: int
    electricity_paise: int


class StatementOut(Schema):
    fy: str
    rent_paise: int
    electricity_paise: int
    deductions_paise: int
    standard_deduction_paise: int
    rows: list[StatementRow]
    note: str


@router.get('/owner/statement', response=StatementOut, summary='Year statement for your CA')
def statement(request, fy: str | None = None):
    p = common.owner_property(request)
    fy = fy or fy_label(today())
    start = date(int(fy[:4]), 4, 1)
    end = date(start.year + 1, 4, 1)
    lines = LedgerLine.objects.filter(organisation=p.organisation, journal__created_at__date__gte=start, journal__created_at__date__lt=end)
    tot = lambda code: -(lines.filter(account__code=code).aggregate(s=Sum('amount_paise'))['s'] or 0)  # noqa: E731
    rows = []
    for b in Booking.objects.filter(bed__room__property=p, invoices__period__gte=start, invoices__period__lt=end).distinct().select_related('guest', 'bed__room'):
        inv_lines = [ln for inv in b.invoices.filter(period__gte=start, period__lt=end) for ln in inv.lines.all()]
        rows.append({'name': b.guest.name, 'room': b.bed.room.number,
                     'rent_paise': sum(ln.amount_paise for ln in inv_lines if ln.kind == 'rent'),
                     'electricity_paise': sum(ln.amount_paise for ln in inv_lines if ln.kind == 'electricity')})
    rent = tot('rent_income')
    return {'fy': fy, 'rent_paise': rent, 'electricity_paise': tot('electricity_income'), 'deductions_paise': tot('deductions_income'),
            'standard_deduction_paise': rent * 30 // 100, 'rows': rows,
            'note': 'The 30% standard deduction applies if you declare rent as income from house property. Your CA decides; '
                    'PG income with services such as meals is often business income instead.'}
