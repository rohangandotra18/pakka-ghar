import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Write the OpenAPI 3.1 contract to contracts/openapi.json (the app generates its client from it).'

    def handle(self, *args, **kw):
        from config.api import api
        out = Path(settings.BASE_DIR).parent / 'contracts' / 'openapi.json'
        out.parent.mkdir(exist_ok=True)
        schema = api.get_openapi_schema()
        out.write_text(json.dumps(schema, indent=2, sort_keys=True, default=str) + '\n')
        self.stdout.write(self.style.SUCCESS(f'{out} · OpenAPI {schema["openapi"]} · {len(schema["paths"])} paths'))
