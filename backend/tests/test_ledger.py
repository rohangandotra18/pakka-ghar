"""AC-16/17: money is integer paise in an append-only, always-balanced ledger."""
import pytest
from django.db import DatabaseError, connection, transaction

from apps.core.ledger import Unbalanced, balance, post, reverse
from apps.core.models import Journal, LedgerLine
from apps.core.rls import system
from apps.payments.services import _tax, gst_rate_bp


def test_unbalanced_journal_is_refused_in_python(world):
    with system(), pytest.raises(Unbalanced):
        post(world['org_a'], 'x', 'bad', [('escrow', None, 100), ('deposit_liability', world['aman'], -99)])


def test_database_refuses_an_unbalanced_journal(world):
    with system():
        j = post(world['org_a'], 'x', 'ok', [('escrow', None, 100), ('deposit_liability', world['aman'], -100)])
        acc = j.lines.first().account
        with pytest.raises(DatabaseError, match='does not balance'), transaction.atomic():
            LedgerLine.objects.create(organisation=world['org_a'], journal=j, account=acc, amount_paise=5)
            with connection.cursor() as c:
                c.execute('SET CONSTRAINTS ALL IMMEDIATE')


@pytest.mark.parametrize('sql', ['UPDATE core_ledgerline SET amount_paise = 1', 'DELETE FROM core_ledgerline', 'DELETE FROM core_journal'])
def test_ledger_is_append_only(world, sql):
    with system():
        post(world['org_a'], 'x', 'ok', [('escrow', None, 100), ('deposit_liability', world['aman'], -100)])
        with pytest.raises(DatabaseError, match='append-only'), transaction.atomic(), connection.cursor() as c:
            c.execute(sql)


def test_reversal_is_a_new_journal(world):
    with system():
        j = post(world['org_a'], 'deposit_captured', 'dep', [('escrow', None, 900000), ('deposit_liability', world['aman'], -900000)])
        r = reverse(j)
        assert Journal.objects.count() == 2 and r.reverses_id == j.id
        assert balance(world['org_a'], 'escrow') == 0


def test_gst_rounding_and_exemption():
    assert _tax(999, 1200) == 120            # 119.88 paise rounds half-up to 120
    assert gst_rate_bp(1000000, 11) == 0     # ₹10,000 for 11 months: exempt
    assert gst_rate_bp(2500000, 11) == 1200  # above ₹20,000 a month
    assert gst_rate_bp(1000000, 2) == 1200   # under 90 days
