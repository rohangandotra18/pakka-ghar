from django.conf import settings
from django.db import migrations

from apps.core.rls import policy_sql


class Migration(migrations.Migration):
    dependencies = [('booking', '0001_initial'), ('core', '0002_security')]

    operations = [
        migrations.RunSQL(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO {settings.DB_SYSTEM_ROLE}', migrations.RunSQL.noop),
        policy_sql('booking_offer', party_cols=('tenant_id',)),
        policy_sql('booking_booking', party_cols=('guest_id',)),
        policy_sql('booking_agreement', party_cols=('tenant_id',)),
        policy_sql('booking_policeverification', party_cols=('tenant_id',)),
        policy_sql('booking_visit', party_cols=('tenant_id',)),
        policy_sql('booking_rating', party_cols=('tenant_id',)),
    ]
