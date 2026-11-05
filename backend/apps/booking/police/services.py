"""Police verification: the packet each city's police ask for, submitted and cleared by the owner."""
from django.utils import timezone

from apps.booking.common import owners_of
from apps.core.api_support import ApiError, audit, notify
from apps.core.models import Party
from apps.jurisdiction.rules import MissingFields, build_packet

from ..models import Booking, PoliceVerification

# ---- police verification ---------------------------------------------------------------------------------

def _packet_inputs(b: Booking) -> tuple[dict, dict]:
    t, p = b.guest, b.bed.room.property
    prof = t.profile or {}
    works = t.works_at or ''
    owner = next(iter(owners_of(b.organisation)), None)
    tenant = {
        'full_name': t.name, 'father_or_guardian_name': prof.get('guardian_name'), 'date_of_birth': prof.get('date_of_birth'),
        'mobile': t.phone, 'permanent_address': prof.get('home_address'), 'previous_address': prof.get('home_address'),
        'emergency_contact': prof.get('emergency_contact'), 'id_type': 'Aadhaar' if t.aadhaar_masked else None,
        'id_last4': t.aadhaar_masked[-4:] if t.aadhaar_masked else None, 'photo': 'selfie on file' if t.selfie_matched_at else None,
        'occupation': 'Student' if any(w in works for w in ('University', 'College', 'Institute', 'School')) else ('Working' if works else None),
        'workplace_or_college': works, 'move_in_on': b.stay_period.lower.date().isoformat(),
    }
    owner_d = {'owner_name': owner.name if owner else None, 'owner_mobile': owner.phone if owner else None,
               'property_address': p.address, 'room_number': b.bed.room.number}
    return tenant, owner_d


def prepare_police(b: Booking) -> PoliceVerification:
    pv = b.police
    tenant, owner = _packet_inputs(b)
    try:
        pv.packet = build_packet(pv.jurisdiction, tenant, owner)
    except MissingFields as e:
        pv.packet = {'missing': e.missing}
    pv.save(update_fields=['packet', 'updated_at'])
    return pv


def submit_police(b: Booking, actor: Party) -> PoliceVerification:
    pv = prepare_police(b)
    if 'missing' in pv.packet:
        raise ApiError(422, 'police_form_incomplete', 'The police form still needs: ' + ', '.join(pv.packet['missing']).replace('_', ' ') + '.')
    if pv.status == 'not_started':
        pv.status, pv.submitted_at = 'submitted', timezone.now()
        pv.save(update_fields=['status', 'submitted_at', 'updated_at'])
        audit(b.organisation, actor, 'police.submit', pv)
    return pv


def mark_police_verified(b: Booking, actor: Party) -> PoliceVerification:
    """A person confirms the police cleared the resident; the app never decides this on its own."""
    pv = b.police
    if pv.status != 'submitted':
        raise ApiError(409, 'submit_first', 'Submit the verification first.')
    pv.status, pv.verified_at, pv.verified_by = 'verified', timezone.now(), actor
    pv.save(update_fields=['status', 'verified_at', 'verified_by', 'updated_at'])
    audit(b.organisation, actor, 'police.verified', pv)
    notify(b.guest, 'police.verified', 'Your police verification is complete.', org=b.organisation)
    return pv
