"""Guards that fail loudly if a later change quietly weakens the design."""
import json
from pathlib import Path

from django.conf import settings
from django.db import connection

# Tables deliberately without row-level security, and why. Anything else must force RLS with a policy.
NO_RLS = {
    'core_party': 'people; only ever exposed through endpoints that pick the fields (names on offers, residents)',
    'core_organisation': 'owner business names; public anyway',
    'core_membership': 'read during sign-in, before any context exists',
    'identity_otpchallenge': 'sign-in codes, hashed; read before the caller is known',
    'identity_sessiontoken': 'session tokens, hashed; read to identify the caller',
    'django_migrations': 'Django',
    'django_content_type': 'Django',
}


def test_every_business_table_forces_row_level_security(db):
    with connection.cursor() as c:
        c.execute("""SELECT c.relname, c.relforcerowsecurity, (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid)
                     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'public' AND c.relkind = 'r'""")
        rows = c.fetchall()
    unprotected = [name for name, forced, policies in rows if name not in NO_RLS and not (forced and policies)]
    assert not unprotected, f'Add a policy_sql migration for: {unprotected}'
    stale = set(NO_RLS) - {name for name, *_ in rows}
    assert not stale, f'Remove from NO_RLS (no such table): {stale}'


def test_the_apps_contract_matches_the_api(db):
    """contracts/openapi.json is what the app's types are generated from. If this fails, run
    `manage.py export_openapi` and `npm run api:types`."""
    from config.api import api
    live = api.get_openapi_schema()
    saved = json.loads((Path(settings.BASE_DIR).parent / 'contracts' / 'openapi.json').read_text())
    strip = lambda paths: {k: v for k, v in paths.items() if not k.startswith('/api/dev/')}  # noqa: E731 - dev-only routes
    assert json.loads(json.dumps(strip(live['paths']), default=str)) == strip(saved['paths'])
    assert json.loads(json.dumps(live['components'], default=str)) == saved['components']
