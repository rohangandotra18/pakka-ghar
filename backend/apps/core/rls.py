"""Row-level security. The database, not the client or the view code, decides what each request can see.

Every request sets two transaction-local settings before touching business tables:
  app.current_org    the organisation the caller is acting for (an owner's PG business), or empty
  app.current_party  the person calling, or empty for someone browsing without an account
Policies (created by the migrations with `policy_sql`) compare each row against them.
"""
from contextlib import contextmanager

from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.operations import RunSQL

FUNCTIONS_SQL = """
CREATE OR REPLACE FUNCTION app_org() RETURNS uuid LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('app.current_org', true), '')::uuid $$;
CREATE OR REPLACE FUNCTION app_party() RETURNS uuid LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('app.current_party', true), '')::uuid $$;
"""


def set_context(org_id=None, party_id=None) -> None:
    """Scope the current transaction. Must run inside transaction.atomic (requests are atomic)."""
    with connection.cursor() as c:
        c.execute(
            "SELECT set_config('app.current_org', %s, true), set_config('app.current_party', %s, true)",
            [str(org_id or ''), str(party_id or '')],
        )


@contextmanager
def system():
    """Bypass row-level security for work that belongs to no single caller: payment webhooks,
    scheduled jobs, public listing aggregates and seeding. Keep these blocks small and explicit."""
    with transaction.atomic():  # a savepoint when nested: rolling it back also undoes SET LOCAL ROLE
        with connection.cursor() as c:
            c.execute('SELECT current_user')
            outer = c.fetchone()[0]
            c.execute(f'SET LOCAL ROLE {settings.DB_SYSTEM_ROLE}')
        yield
        with connection.cursor() as c:
            # back to the caller's role (nested system() blocks stay system until the outermost ends)
            c.execute('RESET ROLE' if outer != settings.DB_SYSTEM_ROLE else f'SET LOCAL ROLE {settings.DB_SYSTEM_ROLE}')


def policy_sql(table: str, *, org: bool = True, party_cols: tuple[str, ...] = (), extra: str = '',
               public: str = '') -> RunSQL:
    """Enable and force RLS on `table` and give it one access policy.

    org         rows of the caller's organisation are visible and writable
    party_cols  rows where any of these columns is the caller are visible and writable
    extra       another SQL condition that grants access (e.g. a resident reading their room's meter)
    public      condition for rows anyone may read, signed in or not (published listings)
    """
    conds = (['organisation_id = app_org()'] if org else []) + [f'{c} = app_party()' for c in party_cols]
    if extra:
        conds.append(f'({extra})')
    cond = ' OR '.join(conds) or 'false'
    forward = [
        f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY',
        f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY',
        f'CREATE POLICY {table}_access ON {table} USING ({cond}) WITH CHECK ({cond})',
    ]
    reverse = [f'DROP POLICY IF EXISTS {table}_access ON {table}', f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY']
    if public:
        forward.append(f'CREATE POLICY {table}_public ON {table} FOR SELECT USING ({public})')
        reverse.insert(0, f'DROP POLICY IF EXISTS {table}_public ON {table}')
    return RunSQL(forward, reverse_sql=reverse)


def immutable_sql(table: str) -> RunSQL:
    """Reject UPDATE and DELETE on an append-only table, for every role."""
    fn = f'{table}_immutable'
    return RunSQL(
        [
            f"""CREATE OR REPLACE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS
                $$ BEGIN RAISE EXCEPTION '{table} is append-only: post a reversal instead'; END $$""",
            f'CREATE TRIGGER {fn} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {fn}()',
        ],
        reverse_sql=[f'DROP TRIGGER IF EXISTS {fn} ON {table}', f'DROP FUNCTION IF EXISTS {fn}()'],
    )
