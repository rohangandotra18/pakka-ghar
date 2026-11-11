"""Haryana RERA, Panchkula bench: the open lists of registered agents and registered projects.

Both lists are plain HTML tables on pages that need no login or CAPTCHA. The per-project search
form does have a CAPTCHA, so it is not used. Reproducing this material needs the Authority's
permission by email (see README), so the source ships with publish=false.
"""
import re

from .base import TableParser, find_date

NAME = "Haryana RERA (Panchkula bench)"
VERIFIED = "2026-10-29"
DEFAULTS = {
    "agents_url": "https://haryanarera.gov.in/admincontrol/registered_agents/1",
    "projects_url": "https://haryanarera.gov.in/admincontrol/registered_projects/1",
    "min_rows": 50,  # a page with fewer rows than this is treated as broken, not as mass removals
}


def _header_index(rows, *must):
    """Finds the header row and maps lower-cased header text to column index."""
    for i, r in enumerate(rows):
        heads = [c["text"].lower() for c in r]
        if all(any(m in h for h in heads) for m in must):
            return i, heads
    raise ValueError("header row with %s not found; the page layout may have changed" % (must,))


def _col(heads, *words):
    for i, h in enumerate(heads):
        if all(w in h for w in words):
            return i
    return None


def _cell(row, i):
    return row[i] if i is not None and i < len(row) else {"text": "", "links": []}


def parse_agents(html, base_url=""):
    p = TableParser(base_url)
    p.feed(html)
    hi, heads = _header_index(p.rows, "registration", "agent name")
    c = {k: _col(heads, *w) for k, w in {
        "reg": ("registration",), "name": ("agent name",), "district": ("district",), "category": ("category",),
        "issued": ("issu",), "expires": ("expiry",), "cert": ("view certificate",), "ext": ("extension",)}.items()}
    out, seen = [], set()
    for r in p.rows[hi + 1:]:
        reg = _cell(r, c["reg"])["text"]
        # Older certificates read "123 OF 2018" or "12-2018" instead of HRERA-PKL-REA-1247-2022; repeated header rows have no serial number.
        if not reg or not r[0]["text"].isdigit():
            continue
        key = reg if reg not in seen else "%s / %s" % (reg, _cell(r, c["name"])["text"])
        seen.add(key)
        out.append({
            "key": key,
            "reg_no": reg,
            "name": _cell(r, c["name"])["text"],
            "district": _cell(r, c["district"])["text"].title(),
            "category": _cell(r, c["category"])["text"],
            "issued": find_date(_cell(r, c["issued"])["text"]),
            "expires": find_date(_cell(r, c["expires"])["text"]),
            "certificate_url": (_cell(r, c["cert"])["links"] or [None])[0],
            "extension_urls": _cell(r, c["ext"])["links"],
        })
    return out


def parse_projects(html, base_url=""):
    p = TableParser(base_url)
    p.feed(html)
    hi, heads = _header_index(p.rows, "registration certificate", "project id")
    c = {k: _col(heads, *w) for k, w in {
        "cert_no": ("registration certificate",), "pid": ("project id",), "name": ("project name",), "builder": ("builder",),
        "location": ("location",), "district": ("district",), "with": ("registered with",), "details": ("details",),
        "valid": ("up-to",), "cert": ("view certificate",), "qpr": ("quarterly",), "orders": ("monitoring",), "oc": ("oc/cc",)}.items()}
    out, seen = [], set()
    for r in p.rows[hi + 1:]:
        if not r[0]["text"].isdigit():
            continue
        pid_cell = _cell(r, c["pid"])
        cert_text = _cell(r, c["cert_no"])["text"]
        # Some older projects show "NA" for the project ID; they are keyed by registration number instead.
        pid = pid_cell["text"] if re.match(r"RERA-[A-Z]+-\d+", pid_cell["text"]) else None
        reg = re.sub(r"\s*Lapsed Project\s*", "", cert_text, flags=re.I).strip()
        key = pid or "REG " + reg
        if not reg and not pid or key in seen:
            continue
        seen.add(key)
        lapsed = "lapsed" in cert_text.lower()
        detail = (pid_cell["links"] or [None])[0]
        m = re.search(r"/(\d+)$", detail or "")
        out.append({
            "key": key,
            "project_id": pid,
            "portal_id": int(m.group(1)) if m else None,
            "registration_no": reg,
            "registered_on": find_date(cert_text),
            "lapsed": lapsed,
            "name": _cell(r, c["name"])["text"],
            "builder": _cell(r, c["builder"])["text"],
            "location": _cell(r, c["location"])["text"],
            "district": _cell(r, c["district"])["text"].title(),
            "registered_with": _cell(r, c["with"])["text"],
            "valid_upto": find_date(_cell(r, c["valid"])["text"]),
            "detail_url": detail,
            "forms_url": (_cell(r, c["details"])["links"] or [None])[0],
            "certificate_url": (_cell(r, c["cert"])["links"] or [None])[0],
            "progress_urls": _cell(r, c["qpr"])["links"],
            "order_urls": _cell(r, c["orders"])["links"],
            "oc_urls": _cell(r, c["oc"])["links"],
        })
    return out


def _sync(ctx, kind, url, parse, key, summary):
    resp = ctx.http.get(url)
    if resp.not_modified:
        ctx.log("%s: not modified since last run" % kind)
        return 0, 0, 0
    html = resp.text()
    ctx.save_probe(kind, html)
    rows = parse(html, url)
    if len(rows) < ctx.cfg["min_rows"]:
        raise ValueError("%s page gave only %d rows (expected at least %d); not updating" % (kind, len(rows), ctx.cfg["min_rows"]))
    added = changed = 0
    keys = []
    for row in rows:
        k = row[key]
        keys.append(k)
        res = ctx.store.upsert(ctx.source, kind, k, row, summary(row))
        added += res == "added"
        changed += res == "changed"
    removed = ctx.store.mark_missing(ctx.source, kind, keys, summary)
    ctx.http.remember(resp)
    ctx.log("%s: %d rows, %d new, %d changed, %d gone" % (kind, len(rows), added, changed, removed))
    return added, changed, removed


def run(ctx):
    totals = [0, 0, 0]
    for kind, url, parse, key, summary in (
        ("agents", ctx.cfg["agents_url"], parse_agents, "key", lambda r: "%s · %s · %s" % (r.get("name"), r.get("district"), r.get("reg_no"))),
        ("projects", ctx.cfg["projects_url"], parse_projects, "key",
         lambda r: "%s by %s · %s · %s" % (r.get("name"), r.get("builder"), r.get("district"), r.get("key"))),
    ):
        for i, n in enumerate(_sync(ctx, kind, url, parse, key, summary)):
            totals[i] += n
    return tuple(totals)
