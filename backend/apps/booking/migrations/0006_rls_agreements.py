from django.conf import settings
from django.db import migrations

from apps.core.rls import immutable_sql, policy_sql


class Migration(migrations.Migration):
    dependencies = [('booking', '0005_agreement_documents')]

    operations = [
        migrations.RunSQL(f'GRANT ALL ON ALL TABLES IN SCHEMA public TO {settings.DB_SYSTEM_ROLE}', migrations.RunSQL.noop),
        policy_sql('booking_agreementtemplate'),
        # the owner, the signer, and the resident whose agreement it is (to see the owner's countersignature)
        policy_sql('booking_signature', party_cols=('party_id',),
                   extra='agreement_id IN (SELECT a.id FROM booking_agreement a WHERE a.tenant_id = app_party())'),
        immutable_sql('booking_signature'),
    ]
