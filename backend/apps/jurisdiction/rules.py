"""Tricity rules: which police force verifies tenants, what its form needs, and the electricity tariff ceiling.

Chandigarh is a Union Territory; Mohali (SAS Nagar) is in Punjab; Panchkula is in Haryana. Each runs its own
tenant-verification process, so a packet is built per city.

VERIFY BEFORE LAUNCH: the field lists and the tariff ceilings below are a starting point. Confirm each against
the current police portal and the latest tariff order of the distribution company, then update this file.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Jurisdiction:
    code: str
    name: str
    state: str
    police: str
    portal: str
    discom: str
    max_tariff_paise: int        # highest per-unit domestic rate a PG may pass on to residents
    tenant_fields: tuple[str, ...]
    owner_fields: tuple[str, ...]


COMMON_TENANT = ('full_name', 'father_or_guardian_name', 'date_of_birth', 'mobile', 'permanent_address',
                 'id_type', 'id_last4', 'photo', 'occupation', 'workplace_or_college', 'move_in_on')
COMMON_OWNER = ('owner_name', 'owner_mobile', 'property_address', 'room_number')

RULES: dict[str, Jurisdiction] = {
    'chandigarh': Jurisdiction(
        code='chandigarh', name='Chandigarh', state='Union Territory of Chandigarh', police='Chandigarh Police',
        portal='Chandigarh Police tenant verification', discom='Chandigarh electricity distribution licensee',
        max_tariff_paise=750, tenant_fields=COMMON_TENANT + ('previous_address',), owner_fields=COMMON_OWNER),
    'mohali': Jurisdiction(
        code='mohali', name='Mohali (SAS Nagar)', state='Punjab', police='Punjab Police',
        portal='PP Saanjh tenant verification', discom='PSPCL',
        max_tariff_paise=800, tenant_fields=COMMON_TENANT + ('previous_address', 'emergency_contact'), owner_fields=COMMON_OWNER),
    'panchkula': Jurisdiction(
        code='panchkula', name='Panchkula', state='Haryana', police='Haryana Police',
        portal='Harsamay tenant verification', discom='UHBVN',
        max_tariff_paise=800, tenant_fields=COMMON_TENANT + ('emergency_contact',), owner_fields=COMMON_OWNER),
}


class MissingFields(ValueError):
    def __init__(self, missing: list[str]):
        super().__init__('Missing: ' + ', '.join(missing))
        self.missing = missing


def build_packet(city: str, tenant: dict, owner: dict) -> dict:
    """Assemble the verification packet for `city`. Raises MissingFields if anything required is blank.
    The ID number itself is never included: only its type and last four digits."""
    j = RULES[city]
    missing = [f for f in j.tenant_fields if not tenant.get(f)] + [f for f in j.owner_fields if not owner.get(f)]
    if missing:
        raise MissingFields(missing)
    return {
        'jurisdiction': j.code, 'police': j.police, 'portal': j.portal,
        'tenant': {f: tenant[f] for f in j.tenant_fields},
        'owner': {f: owner[f] for f in j.owner_fields},
    }


def check_tariff(city: str, tariff_paise: int) -> None:
    j = RULES[city]
    if tariff_paise > j.max_tariff_paise:
        raise ValueError(f'₹{tariff_paise / 100:.2f}/unit is above the {j.discom} ceiling of ₹{j.max_tariff_paise / 100:.2f}.')
