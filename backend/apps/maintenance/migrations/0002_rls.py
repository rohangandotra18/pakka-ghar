from django.conf import settings
from django.db import migrations

from apps.core.rls import policy_sql


class Migration(migrations.Migration):
    dependencies = [('maintenance', '0001_initial'), ('core', '0002_security')]

    operations = [
        migrations.RunSQL(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO {settings.DB_SYSTEM_ROLE}', migrations.RunSQL.noop),
        policy_sql('maintenance_ticket', party_cols=('raised_by_id',)),
        # the owner a report is about must never see it: no organisation clause
        policy_sql('maintenance_trustreport', org=False, party_cols=('reporter_id',)),
    ]
