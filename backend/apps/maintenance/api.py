"""Maintenance requests (resident → owner) and trust reports (anyone → Pakka Ghar only)."""
from datetime import datetime, timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from ninja import Router, Schema

from apps.booking.stay.api import current_booking
from apps.booking.common import owners_of
from apps.core.api_support import ApiError, audit, notify, owner_org, party_of
from apps.core.rls import system
from apps.property.models import Property

from .models import CATEGORIES, Ticket, TrustReport

router = Router(tags=['requests'])
REPORTS_PER_DAY = 5   # trust reports one account may send in 24 hours

# the trade each kind of request needs; the owner's own contact for it is remembered on the property
TRADE = {'Electrical': 'Electrician', 'Plumbing': 'Plumber', 'Wi-Fi': 'Wi-Fi provider', 'Cleaning': 'Housekeeping',
         'Furniture': 'Carpenter', 'Listing issue': 'Caretaker'}


def contact_for(t: Ticket) -> str:
    return (t.property.attributes or {}).get('contacts', {}).get(t.category) or TRADE.get(t.category, 'Caretaker')


class TicketOut(Schema):
    id: str
    ref: str
    who: str
    room: str
    category: str
    text: str
    status: str
    at: datetime
    assignee: str
    suggested_assignee: str
    to_pakka_ghar: bool = False
    photos: list[str] = []


def ticket_out(t: Ticket) -> dict:
    return {'id': str(t.id), 'ref': t.reference, 'who': t.raised_by.name, 'room': t.room.number if t.room else '–', 'category': t.category,
            'text': t.text, 'status': t.status, 'at': t.created_at, 'assignee': t.assignee,
            'suggested_assignee': contact_for(t),
            'photos': [ph.thumb.url if ph.thumb else ph.image.url for ph in t.photos.filter(status='live')]}


def report_out(r: TrustReport) -> dict:
    return {'id': str(r.id), 'ref': f'T-{str(r.id)[:6].upper()}', 'who': r.reporter.name, 'room': '–', 'category': r.category,
            'text': r.text, 'status': 'Raised' if r.status == 'open' else 'Fixed', 'at': r.created_at,
            'assignee': 'Pakka Ghar trust team', 'suggested_assignee': '', 'to_pakka_ghar': True}


class NewRequestIn(Schema):
    category: str
    text: str
    listing: str | None = None   # for a report about a PG the person doesn't live in


@router.post('/requests', response=TicketOut, summary='Raise a repair, or report a listing or a cash request')
def raise_request(request, body: NewRequestIn):
    party = party_of(request)
    text = body.text.strip()
    if not 4 <= len(text) <= 2000:
        raise ApiError(422, 'describe_it', 'Describe the problem in a few words.')
    b = current_booking(party)
    if body.category in ('Listing issue', 'Asked to pay in cash'):
        prop = b.bed.room.property if b else (Property.objects.filter(slug=body.listing).first() if body.listing else None)
        if body.listing and not b and not prop:
            raise ApiError(404, 'not_found', 'No such PG.')
        # each report lands in the trust team's queue: the same one twice adds nothing, and a flood would bury real ones
        same = TrustReport.objects.filter(reporter=party, property=prop, category=body.category, status='open').first()
        if same:
            return report_out(same)
        if TrustReport.objects.filter(reporter=party, created_at__gte=timezone.now() - timedelta(days=1)).count() >= REPORTS_PER_DAY:
            raise ApiError(429, 'too_many_reports', 'You have sent several reports today. The trust team will look at them first.')
        r = TrustReport.objects.create(reporter=party, organisation=prop.organisation if prop else None, property=prop,
                                       category=body.category, text=text)
        if body.category == 'Listing issue' and b:  # residents' listing issues also reach the owner; cash reports never do
            _ticket(b, party, body.category, text)
        return report_out(r)
    if body.category not in CATEGORIES:
        raise ApiError(422, 'bad_category', 'Pick what it is about.')
    if not b or b.status != 'active':
        raise ApiError(409, 'not_living_here', 'Repairs can be raised once you live in the PG.')
    return ticket_out(_ticket(b, party, body.category, text))


def next_number(org) -> int:
    with system():  # numbering is per owner, across all their residents
        return (Ticket.objects.filter(organisation=org).aggregate(m=Max('number'))['m'] or 200) + 1


def _ticket(b, party, category: str, text: str) -> Ticket:
    # Two residents raising a repair at the same moment get the same next number; the unique constraint catches
    # it and the second simply takes the number after.
    for attempt in range(5):
        try:
            with transaction.atomic():
                t = Ticket.objects.create(organisation=b.organisation, number=next_number(b.organisation), property=b.bed.room.property,
                                          room=b.bed.room, raised_by=party, category=category, text=text)
            break
        except IntegrityError:
            if attempt == 4:
                raise
    for o in owners_of(b.organisation):
        notify(o, 'ticket.new', f'{party.first_name}: {category.lower()} in Room {b.bed.room.number}.', org=b.organisation, ticket=str(t.id))
    return t


@router.get('/requests/mine', response=list[TicketOut])
def mine(request):
    party = party_of(request)
    tickets = [ticket_out(t) for t in Ticket.objects.filter(raised_by=party).select_related('room', 'raised_by').order_by('-created_at')]
    reports = [report_out(r) for r in TrustReport.objects.filter(reporter=party).select_related('reporter').order_by('-created_at')]
    return sorted(tickets + reports, key=lambda x: x['at'], reverse=True)


@router.post('/requests/{ticket_id}/confirm', response=TicketOut, summary="The resident confirms it's fixed")
def confirm(request, ticket_id: UUID):
    party = party_of(request)
    t = Ticket.objects.filter(pk=ticket_id, raised_by=party).select_related('room', 'raised_by').first()
    if not t or t.status != 'Fixed':
        raise ApiError(409, 'not_fixed', 'This request is not marked fixed yet.')
    t.status, t.confirmed_at = 'Confirmed', timezone.now()
    t.save(update_fields=['status', 'confirmed_at', 'updated_at'])
    _tell_owners(t, f'{t.raised_by.first_name} confirmed the {t.category.lower()} repair in Room {t.room.number} is fixed.')
    return ticket_out(t)


@router.post('/requests/{ticket_id}/not-fixed', response=TicketOut, summary="The resident says it isn't fixed: back to the owner")
def not_fixed(request, ticket_id: UUID):
    party = party_of(request)
    t = Ticket.objects.select_for_update(of=('self',)).filter(pk=ticket_id, raised_by=party).select_related('room', 'raised_by').first()
    if not t or t.status != 'Fixed':
        raise ApiError(409, 'not_fixed', 'This request is not marked fixed yet.')
    t.status, t.fixed_at = 'Assigned', None   # still with whoever was sent; the owner marks it fixed again
    t.save(update_fields=['status', 'fixed_at', 'updated_at'])
    audit(t.organisation, party, 'ticket.reopen', t)
    _tell_owners(t, f'{t.raised_by.first_name} says the {t.category.lower()} repair in Room {t.room.number} isn’t fixed yet.')
    return ticket_out(t)


def _tell_owners(t: Ticket, title: str) -> None:
    with system():
        owners = owners_of(t.organisation)
    for o in owners:
        notify(o, 'ticket.update', title, org=t.organisation, ticket=str(t.id))


# ---- owner ----------------------------------------------------------------------------------------------

@router.get('/owner/tickets', response=list[TicketOut], tags=['owner'])
def owner_tickets(request):
    org = owner_org(request)
    qs = Ticket.objects.filter(organisation=org).select_related('room', 'raised_by', 'property').order_by('-created_at')
    return [ticket_out(t) for t in qs]


class AssignIn(Schema):
    assignee: str | None = None


def _owned(request, ticket_id) -> Ticket:
    org = owner_org(request)
    t = Ticket.objects.filter(pk=ticket_id, organisation=org).select_related('room', 'raised_by', 'property').first()
    if not t:
        raise ApiError(404, 'not_found', 'No such request.')
    return t


@router.post('/owner/tickets/{ticket_id}/assign', response=TicketOut, tags=['owner'])
def assign(request, ticket_id: UUID, body: AssignIn):
    t = _owned(request, ticket_id)
    if t.status != 'Raised':
        raise ApiError(409, 'already_assigned', 'This request is already assigned.')
    who = (body.assignee or '').strip()[:80] or contact_for(t)
    t.status, t.assignee, t.assigned_at = 'Assigned', who, timezone.now()
    t.save(update_fields=['status', 'assignee', 'assigned_at', 'updated_at'])
    if body.assignee and body.assignee.strip():  # remember the owner's contact for this kind of repair
        p = t.property
        attrs = p.attributes or {}
        attrs['contacts'] = {**attrs.get('contacts', {}), t.category: who}
        p.attributes = attrs
        p.save(update_fields=['attributes', 'updated_at'])
    audit(t.organisation, request.party, 'ticket.assign', t, after={'assignee': t.assignee})
    notify(t.raised_by, 'ticket.assigned', f'{t.assignee} is coming for your {t.category.lower()} request.', org=t.organisation, ticket=str(t.id))
    return ticket_out(t)


@router.post('/owner/tickets/{ticket_id}/fixed', response=TicketOut, tags=['owner'])
def fixed(request, ticket_id: UUID):
    t = _owned(request, ticket_id)
    if t.status != 'Assigned':
        raise ApiError(409, 'assign_first', 'Assign someone first.')
    t.status, t.fixed_at = 'Fixed', timezone.now()
    t.save(update_fields=['status', 'fixed_at', 'updated_at'])
    notify(t.raised_by, 'ticket.fixed', f'Your {t.category.lower()} request is marked fixed. Confirm in the app.', org=t.organisation, ticket=str(t.id))
    return ticket_out(t)
