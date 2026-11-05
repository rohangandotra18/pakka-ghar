"""A small world for each test: two owners, a PG each, two tenants. Built with the system role because row-level
security is forced on every business table, even in tests."""
import secrets
from datetime import date

import pytest
from django.test import Client
from django.utils import timezone

from apps.core.api_support import sha256
from .factories import make_property, org_with_owner, person
from apps.core.rls import system
from apps.identity.models import SessionToken


def token_for(party) -> str:
    t = secrets.token_urlsafe(16)
    with system():
        SessionToken.objects.create(party=party, token_hash=sha256(t))
    return t


class Api:
    """The Django test client with a bearer token and JSON in and out."""
    def __init__(self, token=None):
        self.c, self.token = Client(), token

    def _h(self, idem):
        h = {}
        if self.token:
            h['HTTP_AUTHORIZATION'] = f'Bearer {self.token}'
        if idem:
            h['HTTP_IDEMPOTENCY_KEY'] = idem
        return h

    def get(self, path):
        return self.c.get('/api' + path, **self._h(None))

    def post(self, path, body=None, idem=None):
        return self.c.post('/api' + path, body if body is not None else {}, content_type='application/json', **self._h(idem))

    def patch(self, path, body):
        return self.c.patch('/api' + path, body, content_type='application/json', **self._h(None))

    def put(self, path, body):
        return self.c.put('/api' + path, body, content_type='application/json', **self._h(None))

    def delete(self, path):
        return self.c.delete('/api' + path, **self._h(None))


@pytest.fixture
def world(db):
    with system():
        owner_a, owner_b = person('Jatinder Sidhu', '+919814011150'), person('Gurnoor Kaur', '+919814022260')
        org_a, org_b = org_with_owner('Sidhu Boys PG', owner_a), org_with_owner('Gurnoor Girls PG', owner_b)
        a = make_property(org_a, 'sidhu', 'Sidhu Boys PG', 'Boys', 'Sector 15', 'House 1150, Sector 15-B', 'chandigarh',
                          30.7543, 76.7713, '3 meals', [('101', 'double', 9000), ('104', 'triple', 9000)])
        b = make_property(org_b, 'gurnoor', 'Gurnoor Girls PG', 'Girls', 'Sector 15', 'House 2208, Sector 15-C', 'chandigarh',
                          30.7509, 76.7740, '3 meals', [('204', 'triple', 10000)])
        simran = person('Simran Kaur', '+919876543210', works_at='Chandigarh University')
        aman = person('Aman Verma', '+919876500001')
        unverified = person('Ishaan Malik', '+919876500002', verified=False)
    return {'owner_a': owner_a, 'owner_b': owner_b, 'org_a': org_a, 'org_b': org_b, 'a': a, 'b': b,
            'simran': simran, 'aman': aman, 'unverified': unverified,
            'api': lambda p: Api(token_for(p)), 'anon': Api()}


def read(fn):
    """Read rows without row-level security, for assertions."""
    with system():
        return fn()


@pytest.fixture
def today():
    return timezone.localdate()


__all__ = ['date', 'read']
