"""A person's rights over their data (Digital Personal Data Protection Act, 2023): see everything held about them,
and erase their account.

Erasure removes what identifies the person: name, phone, ID details, police-form details, notifications and sign-in
codes. Bookings, invoices, payments and the ledger stay, linked to an anonymous id, because tenancy, tax and payment
records must be kept by law (VERIFY the retention periods with counsel before launch).
"""
from django.db.models import Q, Sum
from django.utils import timezone
from ninja import Router, Schema

from apps.booking.models import Application, ApplicationMember, Booking, Rating, Signature, Visit
from apps.core.api_support import ApiError, audit, notify, party_of
from apps.core.models import LedgerLine, Membership, Notification
from apps.core.rls import system
from apps.maintenance.models import Ticket, TrustReport
from apps.payments.models import Invoice, Payment

from .models import OtpChallenge, SessionToken

router = Router(tags=['identity'])


def _iso(v):
    return v.isoformat() if hasattr(v, 'isoformat') else v


@router.get('/me/data', response=dict, summary='Everything Pakka Ghar holds about you, as JSON')
def export(request):
    """Read with the caller's own row-level security, so it can only ever contain their rows."""
    p = party_of(request)
    out = {
        'exported_at': timezone.now().isoformat(),
        'profile': {'phone': p.phone, 'name': p.name, 'works_at': p.works_at, 'looking_for': p.looking_for,
                    'move_in_on': _iso(p.move_in_on), 'aadhaar_last4': p.aadhaar_masked[-4:] if p.aadhaar_masked else None,
                    'digilocker_ref': p.digilocker_ref, 'verified_at': _iso(p.kyc_verified_at), 'police_form': p.profile or {},
                    'created_at': p.created_at.isoformat()},
        'sessions': [{'device': t.device, 'created_at': t.created_at.isoformat(), 'last_used_at': _iso(t.last_used_at),
                      'revoked_at': _iso(t.revoked_at)} for t in p.tokens.all()],
        'bookings': [{'reference': b.reference, 'pg': b.bed.room.property.name, 'room': b.bed.room.number, 'status': b.status,
                      'from': b.stay_period.lower.isoformat(), 'to': _iso(b.stay_period.upper), 'rent_paise': b.rent_paise,
                      'deposit_paise': b.deposit_paise, 'deposit_outcome': b.deposit_outcome}
                     for b in Booking.objects.filter(guest=p).select_related('bed__room__property')],
        'applications': [{'pg': a.property.name, 'room': a.room.number if a.room else None, 'bid_paise': a.amount_paise, 'months': a.months,
                          'move_in_on': a.move_in_on.isoformat(), 'status': a.status, 'created_at': a.created_at.isoformat()}
                         for a in Application.objects.filter(lead=p).select_related('property', 'room')],
        'visits': [{'pg': v.property.name, 'slot': v.slot.isoformat(), 'status': v.status} for v in Visit.objects.filter(tenant=p).select_related('property')],
        'invoices': [{'number': i.number, 'period': i.period.isoformat(), 'status': i.status, 'total_paise': i.total_paise}
                     for i in Invoice.objects.filter(party=p).prefetch_related('lines')],
        'payments': [{'purpose': x.purpose, 'amount_paise': x.amount_paise, 'method': x.method, 'status': x.status,
                      'captured_at': _iso(x.captured_at)} for x in Payment.objects.filter(party=p)],
        'ratings_given': [{'score': float(r.score), 'aspects': r.aspects, 'comment': r.comment, 'created_at': r.created_at.isoformat()}
                          for r in Rating.objects.filter(tenant=p, direction='tenant_to_pg')],
        'requests': [{'category': t.category, 'text': t.text, 'status': t.status, 'created_at': t.created_at.isoformat()}
                     for t in Ticket.objects.filter(raised_by=p)],
        'reports': [{'category': r.category, 'text': r.text, 'status': r.status, 'created_at': r.created_at.isoformat()}
                    for r in TrustReport.objects.filter(reporter=p)],
        'groups_joined': [{'pg': m.application.property.name, 'status': m.status, 'joined_at': _iso(m.joined_at)}
                          for m in ApplicationMember.objects.filter(party=p, is_lead=False).select_related('application__property')],
        'signatures': [{'role': s.role, 'typed_name': s.typed_name, 'document_sha256': s.document_sha256, 'ip': s.ip,
                        'device': s.user_agent, 'signed_at': s.signed_at.isoformat()} for s in Signature.objects.filter(party=p)],
        'ratings_received': [{'score': float(r.score), 'comment': r.comment, 'created_at': r.created_at.isoformat()}
                             for r in Rating.objects.filter(tenant=p, direction='owner_to_tenant')],
        'notifications': [{'title': n.title, 'created_at': n.created_at.isoformat()} for n in Notification.objects.filter(party=p)],
    }
    return out


class DeleteIn(Schema):
    confirm: str   # must be the word DELETE


class DeleteOut(Schema):
    deleted: bool
    kept: list[str]


@router.post('/me/delete', response=DeleteOut, summary='Erase your account (refused while you have a stay, money held or a PG)')
def delete(request, body: DeleteIn):
    p = party_of(request)
    if body.confirm != 'DELETE':
        raise ApiError(422, 'confirm', 'Type DELETE to confirm.')
    with system():  # what is owed either way, across every owner
        if Booking.objects.filter(guest=p, status__in=['hold', 'confirmed', 'active']).exists():
            raise ApiError(409, 'stay_open', 'You have a booking or a stay. End or cancel it first.')
        held = LedgerLine.objects.filter(party=p, account__code='deposit_liability').aggregate(s=Sum('amount_paise'))['s'] or 0
        if held:
            raise ApiError(409, 'deposit_held', 'Your deposit is still in escrow. It must be returned before the account can go.')
        if Invoice.objects.filter(party=p, status='open').exists():
            raise ApiError(409, 'bill_open', 'You have an unpaid bill.')
        if Membership.objects.filter(party=p).exists():
            raise ApiError(409, 'owns_pg', 'You manage a PG. Hand it over or close it with the trust team first.')
        Application.objects.filter(lead=p, status__in=['forming', 'pending']).update(status='withdrawn', decided_at=timezone.now())
        # seats are found by account or by number (an invite that was never answered, or turned down, has no account)
        mine = Q(party=p) | Q(phone=p.phone)
        seats = list(ApplicationMember.objects.filter(mine, status__in=['invited', 'joined', 'declined'],
                                                      application__status__in=['forming', 'pending']).select_related('application'))
        ApplicationMember.objects.filter(pk__in=[m.pk for m in seats]).update(status='left')
        ApplicationMember.objects.filter(mine).update(phone='del-' + p.id.hex[:12])
        from apps.booking.applications.services import refresh_after_leaving
        for m in seats:   # the others may now all have joined: send it to the owner instead of leaving it waiting
            refresh_after_leaving(m.application)
        for v in Visit.objects.filter(tenant=p, status__in=['requested', 'confirmed'], slot__gte=timezone.now()).select_related('property'):
            v.status = 'cancelled'
            v.save(update_fields=['status', 'updated_at'])
            from apps.booking.common import owners_of
            for o in owners_of(v.organisation):
                notify(o, 'visit.cancelled', 'A tour was cancelled: the tenant closed their account.', org=v.organisation)
        Notification.objects.filter(party=p).delete()
        OtpChallenge.objects.filter(phone=p.phone).delete()
        SessionToken.objects.filter(party=p, revoked_at__isnull=True).update(revoked_at=timezone.now())
        audit(None, p, 'account.erase', p)
        p.phone = 'del-' + p.id.hex[:12]
        p.name, p.works_at, p.looking_for, p.move_in_on = 'Deleted user', '', '', None
        p.aadhaar_masked = p.digilocker_ref = ''
        p.kyc_verified_at = p.selfie_matched_at = None
        p.profile = {}
        p.save()
    return {'deleted': True, 'kept': ['bookings', 'invoices', 'payments', 'ledger', 'ratings']}
