"""The balanced-journal check fires at COMMIT, by which time the caller's own role and row-level security
apply again and could hide lines of the journal. Run it as the system role so it always sees every line."""
from django.conf import settings
from django.db import migrations

SYS = settings.DB_SYSTEM_ROLE


class Migration(migrations.Migration):
    dependencies = [('core', '0002_security')]

    operations = [
        migrations.RunSQL([
            f'GRANT CREATE ON SCHEMA public TO {SYS}',
            'ALTER FUNCTION ledger_journal_balanced() SECURITY DEFINER SET search_path = public',
            f'ALTER FUNCTION ledger_journal_balanced() OWNER TO {SYS}',
        ], reverse_sql=['ALTER FUNCTION ledger_journal_balanced() SECURITY INVOKER']),
    ]
