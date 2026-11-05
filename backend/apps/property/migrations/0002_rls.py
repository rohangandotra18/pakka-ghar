from django.conf import settings
from django.db import migrations

from apps.core.rls import policy_sql

LISTED = "p.status <> 'draft'"
RESIDENT_OF_ROOM = ("EXISTS (SELECT 1 FROM booking_booking b JOIN property_bed bd ON bd.id = b.bed_id "
                    "WHERE bd.room_id = {room} AND b.guest_id = app_party() AND b.status IN ('confirmed', 'active'))")


class Migration(migrations.Migration):
    dependencies = [('property', '0001_initial'), ('booking', '0001_initial'), ('core', '0002_security')]

    operations = [
        migrations.RunSQL(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO {settings.DB_SYSTEM_ROLE}', migrations.RunSQL.noop),
        # listings are public once submitted; drafts only to their owner
        policy_sql('property_property', public="status <> 'draft'"),
        policy_sql('property_room', public=f'EXISTS (SELECT 1 FROM property_property p WHERE p.id = property_id AND {LISTED})'),
        policy_sql('property_bed', public='EXISTS (SELECT 1 FROM property_room r JOIN property_property p ON p.id = r.property_id '
                                          f'WHERE r.id = room_id AND {LISTED})'),
        # residents read their own room's meter and readings, nothing else
        policy_sql('property_meter', public=RESIDENT_OF_ROOM.format(room='room_id')),
        policy_sql('property_meterreading', public=RESIDENT_OF_ROOM.format(
            room='(SELECT m.room_id FROM property_meter m WHERE m.id = meter_id)')),
        policy_sql('property_ownershipdocument'),
        policy_sql('property_payoutaccount'),
    ]
