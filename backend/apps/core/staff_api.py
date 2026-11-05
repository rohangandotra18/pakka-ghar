"""The Pakka Ghar trust team: checks new PGs before they go live, and acts on listing and cash reports.
Staff are members of the platform organisation (create one with `manage.py make_staff <phone>`). Their work spans
every owner, so each endpoint checks the caller is staff and then uses the system role."""
from datetime import datetime
from uuid import UUID

from django.utils import timezone
from ninja import Router, Schema

from apps.booking.common import owners_of
from apps.maintenance.models import TrustReport
from apps.property.models import OwnershipDocument, PayoutAccount, Property

from .api_support import ApiError, audit, notify, party_of
from .models import Membership
from .rls import system

router = Router(tags=['staff'])


def staff(request):
    party = party_of(request)
    with system():
        ok = Membership.objects.filter(party=party, organisation__kind='platform', role='staff').exists()
    if not ok:
        raise ApiError(403, 'not_staff', 'Only the Pakka Ghar trust team can do this.')
    return party


class PendingProperty(Schema):
    id: str
    name: str
    owner: str
    owner_phone: str
    address: str
    city: str
    pinned: bool
    rooms: int
    beds: int
    documents: dict[str, str]
    payout: bool
    no_cash_pledged: bool
    submitted_at: datetime


class ReportOut(Schema):
    id: UUID
    category: str
    text: str
    listing: str | None
    reporter: str
    status: str
    created_at: datetime


class QueueOut(Schema):
    properties: list[PendingProperty]
    reports: list[ReportOut]


def _pending(p: Property) -> dict:
    owner = next(iter(owners_of(p.organisation)), None)
    return {'id': p.slug, 'name': p.name, 'owner': owner.name if owner else '', 'owner_phone': owner.phone if owner else '',
            'address': p.address, 'city': p.city, 'pinned': p.lat is not None, 'rooms': p.rooms.count(),
            'beds': sum(r.beds.count() for r in p.rooms.all()),
            'documents': {d.kind: d.status for d in p.documents.all()},
            'payout': PayoutAccount.objects.filter(organisation=p.organisation).exists(),
            'no_cash_pledged': p.organisation.no_cash_pledged_at is not None, 'submitted_at': p.updated_at}


def _report(r: TrustReport) -> dict:
    return {'id': r.id, 'category': r.category, 'text': r.text, 'listing': r.property.slug if r.property else None,
            'reporter': r.reporter.name or r.reporter.phone, 'status': r.status, 'created_at': r.created_at}


@router.get('/staff/queue', response=QueueOut, summary='PGs waiting for a check, and open reports')
def queue(request):
    staff(request)
    with system():
        props = [_pending(p) for p in Property.objects.filter(status='submitted').select_related('organisation').order_by('updated_at')]
        reports = [_report(r) for r in TrustReport.objects.filter(status='open').select_related('reporter', 'property').order_by('created_at')]
    return {'properties': props, 'reports': reports}


def _prop(slug: str) -> Property:
    p = Property.objects.filter(slug=slug).select_related('organisation').first()
    if not p:
        raise ApiError(404, 'not_found', 'No such PG.')
    return p


@router.post('/staff/properties/{slug}/approve', response=PendingProperty, summary='Papers checked: publish the PG')
def approve(request, slug: str):
    who = staff(request)
    with system():
        p = _prop(slug)
        if p.status != 'submitted':
            raise ApiError(409, 'not_submitted', 'This PG is not waiting for a check.')
        if p.lat is None or not p.rooms.exists():
            raise ApiError(409, 'incomplete', 'It needs a map pin and at least one room before it can go live.')
        now = timezone.now()
        p.status, p.published_at = 'published', now
        p.attributes = {k: v for k, v in (p.attributes or {}).items() if k != 'review_note'}
        p.save(update_fields=['status', 'published_at', 'attributes', 'updated_at'])
        org = p.organisation
        org.verified_at = org.verified_at or now
        org.save(update_fields=['verified_at'])
        OwnershipDocument.objects.filter(property=p, status='uploaded').update(status='accepted', updated_at=now)
        audit(org, who, 'property.approve', p)
        for o in owners_of(org):
            notify(o, 'property.live', f'{p.name} is verified and live. Tenants can find and book it now.', org=org)
        return _pending(p)


class RejectIn(Schema):
    reason: str


@router.post('/staff/properties/{slug}/reject', response=PendingProperty, summary='Send the PG back to its owner with the reason')
def reject(request, slug: str, body: RejectIn):
    who = staff(request)
    if not body.reason.strip():
        raise ApiError(422, 'give_reason', 'Tell the owner what to fix.')
    with system():
        p = _prop(slug)
        if p.status != 'submitted':
            raise ApiError(409, 'not_submitted', 'This PG is not waiting for a check.')
        p.status = 'draft'
        p.attributes = {**(p.attributes or {}), 'review_note': body.reason.strip()[:500]}
        p.save(update_fields=['status', 'attributes', 'updated_at'])
        audit(p.organisation, who, 'property.reject', p, after={'reason': body.reason.strip()})
        for o in owners_of(p.organisation):
            notify(o, 'property.rejected', f'{p.name} needs changes: {body.reason.strip()}', org=p.organisation)
        return _pending(p)


class ResolveIn(Schema):
    outcome: str  # confirmed | dismissed


@router.post('/staff/reports/{report_id}/resolve', response=ReportOut, summary='Close a report. A confirmed cash report pauses the listing.')
def resolve(request, report_id: UUID, body: ResolveIn):
    who = staff(request)
    if body.outcome not in ('confirmed', 'dismissed'):
        raise ApiError(422, 'bad_outcome', 'Choose confirmed or dismissed.')
    with system():
        r = TrustReport.objects.select_related('reporter', 'property__organisation').filter(pk=report_id).first()
        if not r or r.status != 'open':
            raise ApiError(404, 'not_found', 'No open report with that id.')
        r.status = body.outcome
        r.save(update_fields=['status', 'updated_at'])
        p = r.property
        if body.outcome == 'confirmed' and r.category == 'Asked to pay in cash' and p and p.status == 'published':
            p.status = 'paused'
            p.save(update_fields=['status', 'updated_at'])
            audit(p.organisation, who, 'property.pause', p, after={'report': str(r.id)})
            for o in owners_of(p.organisation):
                notify(o, 'property.paused', f'{p.name} is paused: a request for cash was confirmed. Contact the trust team.', org=p.organisation)
        notify(r.reporter, 'report.resolved', 'Thanks for your report. We checked it and took action.' if body.outcome == 'confirmed'
               else 'Thanks for your report. We checked it and found no problem.')
        return _report(r)
