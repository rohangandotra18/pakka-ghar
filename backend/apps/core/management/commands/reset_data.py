from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Empty every table (development only). Needs --yes.'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true')

    def handle(self, *args, yes=False, **kw):
        from django.conf import settings
        if not settings.DEBUG or not yes:
            self.stderr.write('Refusing: run with DEBUG=1 and --yes.')
            return
        with transaction.atomic(), connection.cursor() as c:  # as the table owner: TRUNCATE needs ownership
            c.execute("""SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables WHERE schemaname = 'public'
                         AND tablename NOT LIKE 'django_%%'""")
            c.execute(f'TRUNCATE {c.fetchone()[0]} RESTART IDENTITY CASCADE')
        self.stdout.write(self.style.SUCCESS('Every table is empty.'))
