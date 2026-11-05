from django.conf import settings
from django.db import migrations

from apps.core.rls import policy_sql


class Migration(migrations.Migration):
    dependencies = [('payments', '0001_initial'), ('core', '0002_security')]

    operations = [
        migrations.RunSQL(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO {settings.DB_SYSTEM_ROLE}', migrations.RunSQL.noop),
        policy_sql('payments_invoice', party_cols=('party_id',)),
        policy_sql('payments_invoiceline', party_cols=('party_id',)),
        policy_sql('payments_payment', party_cols=('party_id',)),
        policy_sql('payments_reminder'),
        policy_sql('payments_electricityrun'),
        policy_sql('payments_webhookevent', org=False),  # system role only
    ]
