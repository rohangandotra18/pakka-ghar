"""Generic notice and document harvester for authority websites (GMADA, PUDA, HSVP, Chandigarh, Punjab RERA).

It reads each configured index page, keeps links whose text, URL or surrounding row looks relevant
(layouts, zoning, schemes, auctions, draws, allotments, collector rates), records them with any
date found nearby, and optionally downloads new PDFs. Page layouts on these sites change often, so
nothing here depends on a particular table structure.

These sites refuse connections from outside India, so the module was written without seeing their
current pages. Run `python3 fetcher.py run --source <id> --probe` on the Mac first: the probe saves
each page so the keyword list and index URLs can be tuned.
"""
import hashlib
import os
import re
import urllib.parse

from .base import FetchError, LinkParser, find_date

DOC_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".dwg", ".kmz", ".kml", ".zip", ".xlsx", ".xls", ".doc", ".docx")
DEFAULT_KEYWORDS = [
    "layout", "zoning", "zone plan", "master plan", "sector", "scheme", "auction", "e-auction", "draw", "allot",
    "brochure", "plot", "booth", "sco", "site", "collector rate", "reserve price", "lease", "conversion",
    "freehold", "notice", "public notice", "tender",
]


def relevant(link, keywords, same_site):
    url_l = link["url"].lower()
    text = (link["text"] + " " + link.get("context", "")).lower()
    if not url_l.startswith(("http://", "https://")):
        return False
    if not same_site(link["url"]) and not url_l.split("?")[0].endswith(DOC_EXT):
        return False
    is_doc = url_l.split("?")[0].endswith(DOC_EXT)
    hit = any(k in text or k.replace(" ", "-") in url_l or k.replace(" ", "_") in url_l for k in keywords)
    return hit and (is_doc or len(link["text"]) > 12)


def harvest(html, page_url, keywords, allowed_hosts):
    p = LinkParser(page_url)
    p.feed(html)
    hosts = {h.lower() for h in allowed_hosts}

    def same_site(u):
        h = urllib.parse.urlsplit(u).netloc.lower()
        return any(h == x or h.endswith("." + x) for x in hosts)

    seen, out = set(), []
    for l in p.links:
        u = l["url"].split("#")[0]
        if u in seen or u == page_url or not relevant(l, keywords, same_site):
            continue
        seen.add(u)
        path = urllib.parse.urlsplit(u).path.lower()
        out.append({
            "url": u,
            "title": l["text"][:300] or os.path.basename(path),
            "context": l.get("context", "")[:500],
            "date": find_date(l["text"]) or find_date(l.get("context", "")),
            "type": os.path.splitext(path)[1].lstrip(".") or "page",
            "index": page_url,
        })
    return out


def _download(ctx, rec):
    """Saves a new or changed document under data/docs/<source>/ and returns (sha256, path, bytes)."""
    resp = ctx.http.get(rec["url"], conditional=False, max_bytes=int(ctx.global_cfg.get("max_download_mb", 40)) * 1_000_000)
    sha = hashlib.sha256(resp.body).hexdigest()
    name = re.sub(r"[^\w.-]+", "_", os.path.basename(urllib.parse.urlsplit(rec["url"]).path))[-120:] or "document"
    folder = os.path.join(ctx.data_dir, "docs", ctx.source)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, sha[:12] + "_" + name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(resp.body)
    return sha, os.path.relpath(path, ctx.data_dir), len(resp.body)


def run(ctx):
    cfg = ctx.cfg
    keywords = [k.lower() for k in cfg.get("keywords") or DEFAULT_KEYWORDS]
    hosts = cfg.get("hosts") or sorted({urllib.parse.urlsplit(u).netloc for u in cfg["pages"]})
    added = changed = removed = 0
    errors = []
    for page in cfg["pages"]:
        try:
            resp = ctx.http.get(page)
        except FetchError as e:
            errors.append(str(e))
            ctx.log("skipped %s: %s" % (page, e))
            continue
        if resp.not_modified:
            ctx.log("%s: not modified" % page)
            continue
        html = resp.text()
        ctx.save_probe(page, html)
        found = harvest(html, page, keywords, hosts)
        ctx.log("%s: %d relevant links" % (page, len(found)))
        for rec in found:
            if not ctx.http.allowed(rec["url"]):
                continue
            prior = ctx.store.get(ctx.source, "documents", rec["url"])
            if cfg.get("download") and rec["type"] in ("pdf", "kmz", "kml", "dwg", "zip", "xlsx", "xls") and not ctx.probe:
                if prior and prior.get("sha256"):
                    rec.update({k: prior[k] for k in ("sha256", "file", "bytes") if k in prior})
                else:
                    try:
                        rec["sha256"], rec["file"], rec["bytes"] = _download(ctx, rec)
                    except FetchError as e:
                        rec["download_error"] = str(e)[:200]
            res = ctx.store.upsert(ctx.source, "documents", rec["url"], rec, "%s%s" % (rec["title"][:120], " · " + rec["date"] if rec["date"] else ""))
            added += res == "added"
            changed += res == "changed"
        ctx.http.remember(resp)
    if errors and len(errors) == len(cfg["pages"]):
        raise FetchError("; ".join(errors))
    return added, changed, removed
