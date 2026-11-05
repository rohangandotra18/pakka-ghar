"""Posting to the append-only ledger. Balances are always computed from lines, never stored."""
from django.db.models import Sum

from .models import Account, Journal, LedgerLine, Organisation, Party

# (account code, party or None, amount in paise: debit +, credit -)
Line = tuple[str, Party | None, int]


class Unbalanced(ValueError):
    pass


def account(org: Organisation, code: str, party: Party | None = None) -> Account:
    acc, _ = Account.objects.get_or_create(organisation=org, code=code, party=party)
    return acc


def post(org: Organisation, kind: str, memo: str, lines: list[Line], ref: str = '', reverses: Journal | None = None) -> Journal:
    lines = [ln for ln in lines if ln[2]]
    if not lines or sum(a for _, _, a in lines) != 0:
        raise Unbalanced(f'{kind}: lines must be non-empty and sum to zero, got {lines!r}')
    j = Journal.objects.create(organisation=org, kind=kind, memo=memo[:200], ref=ref, reverses=reverses)
    LedgerLine.objects.bulk_create([
        LedgerLine(organisation=org, journal=j, account=account(org, code, party), party=party, amount_paise=amt)
        for code, party, amt in lines
    ])
    return j


def reverse(j: Journal, memo: str = '') -> Journal:
    """A contra-entry: the same lines with the signs flipped. The original stays untouched."""
    lines = [(ln.account.code, ln.party, -ln.amount_paise) for ln in j.lines.select_related('account', 'party')]
    return post(j.organisation, f'{j.kind}_reversal', memo or f'Reversal of {j.memo}', lines, ref=j.ref, reverses=j)


def balance(org: Organisation, code: str, party: Party | None = None) -> int:
    q = LedgerLine.objects.filter(organisation=org, account__code=code)
    if party is not None:
        q = q.filter(party=party)
    return q.aggregate(s=Sum('amount_paise'))['s'] or 0
