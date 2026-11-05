from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Membership, Organisation, Party
from apps.core.rls import system
from apps.identity.services import normalise_phone


class Command(BaseCommand):
    help = 'Make the person with this mobile number a member of the Pakka Ghar trust team.'

    def add_arguments(self, parser):
        parser.add_argument('phone')
        parser.add_argument('--name', default='')

    def handle(self, *args, phone, name, **kw):
        with transaction.atomic(), system():
            org, _ = Organisation.objects.get_or_create(kind='platform', defaults={'name': 'Pakka Ghar trust team'})
            party, _ = Party.objects.get_or_create(phone=normalise_phone(phone), defaults={'name': name})
            Membership.objects.get_or_create(party=party, organisation=org, defaults={'role': 'staff'})
        self.stdout.write(self.style.SUCCESS(f'{party.phone} is on the trust team.'))
