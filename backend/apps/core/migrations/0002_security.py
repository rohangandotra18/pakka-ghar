"""Row-level security, append-only tables and the balanced-journal rule for the core tables."""
from django.conf import settings
from django.db import migrations

from apps.core.rls import FUNCTIONS_SQL, immutable_sql, policy_sql

SYS = settings.DB_SYSTEM_ROLE

GRANTS = [
    f'GRANT USAGE ON SCHEMA public TO {SYS}',
    f'GRANT ALL ON ALL TABLES IN SCHEMA public TO {SYS}',
    f'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {SYS}',
    f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {SYS}',
    f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {SYS}',
]

BALANCED = """
CREATE OR REPLACE FUNCTION ledger_journal_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE total bigint;
BEGIN
  SELECT COALESCE(SUM(amount_paise), 0) INTO total FROM core_ledgerline WHERE journal_id = NEW.journal_id;
  IF total <> 0 THEN
    RAISE EXCEPTION 'journal % does not balance: % paise', NEW.journal_id, total;
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ledger_journal_balanced AFTER INSERT ON core_ledgerline
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ledger_journal_balanced();
"""


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]

    operations = [
        migrations.RunSQL(GRANTS, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(FUNCTIONS_SQL, reverse_sql='DROP FUNCTION IF EXISTS app_org(); DROP FUNCTION IF EXISTS app_party();'),
        policy_sql('core_auditevent', party_cols=('actor_id',)),
        policy_sql('core_idempotencyrecord', party_cols=('party_id',)),
        policy_sql('core_notification', org=False, party_cols=('party_id',)),
        policy_sql('core_account', party_cols=('party_id',)),
        policy_sql('core_journal'),
        policy_sql('core_ledgerline', party_cols=('party_id',)),
        immutable_sql('core_ledgerline'),
        immutable_sql('core_journal'),
        immutable_sql('core_auditevent'),
        migrations.RunSQL(BALANCED, reverse_sql='DROP TRIGGER IF EXISTS ledger_journal_balanced ON core_ledgerline; DROP FUNCTION IF EXISTS ledger_journal_balanced();'),
    ]
