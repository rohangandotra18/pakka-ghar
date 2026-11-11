import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.rls import system
from apps.property.models import Place

DEFAULT = Path(__file__).resolve().parents[2] / 'data' / 'tricity_places.json'
FIELDS = ('kind', 'lat', 'lng', 'aliases', 'popular_rank', 'source')


class Command(BaseCommand):
    help = ('Make the places table match the JSON extract: add new places, update existing ones, and delete places '
            'from the same source (osm) that are no longer in the file. Safe to repeat.')

    def add_arguments(self, parser):
        parser.add_argument('path', nargs='?', default=str(DEFAULT))

    def handle(self, *args, path, **kw):
        try:
            places = json.loads(Path(path).read_text())['places']
        except (OSError, ValueError, KeyError) as e:
            raise CommandError(f'Cannot read places from {path}: {e}')
        added = updated = 0
        with system():   # one transaction: a failure leaves the table as it was
            for p in places:
                defaults = {k: p.get(k) for k in FIELDS if k in p or k == 'popular_rank'}
                _, created = Place.objects.update_or_create(name=p['name'], city=p['city'], defaults=defaults)
                added += created
                updated += not created
            keep = {(p['name'], p['city']) for p in places}
            gone = [pl.pk for pl in Place.objects.filter(source='osm') if (pl.name, pl.city) not in keep]
            Place.objects.filter(pk__in=gone).delete()   # only OSM rows: places added another way stay
        self.stdout.write(self.style.SUCCESS(f'Places: {added} added, {updated} updated, {len(gone)} removed.'))
