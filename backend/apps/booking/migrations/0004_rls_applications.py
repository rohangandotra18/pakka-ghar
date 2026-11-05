from django.conf import settings
from django.db import migrations

from apps.core.rls import policy_sql


class Migration(migrations.Migration):
    dependencies = [('booking', '0003_remove_booking_offer_visit_decided_at_visit_note_and_more')]

    operations = [
        migrations.RunSQL(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO {settings.DB_SYSTEM_ROLE}', migrations.RunSQL.noop),
        # the owner's organisation and the person who applied; roommates read theirs by seat with the system role
        policy_sql('booking_application', party_cols=('lead_id',)),
        # a seat: the owner, the person in it, and the lead of its application
        policy_sql('booking_applicationmember', party_cols=('party_id',),
                   extra='application_id IN (SELECT a.id FROM booking_application a WHERE a.lead_id = app_party())'),
    ]
