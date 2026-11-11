"""Exports the store.

- CSV per source and kind, for your own review (every source, published or not).
- Site import batches for sources marked publish=true: JSON documents for the site's `ref` collection
  plus batch files of at most 50 writes, in the shape a Claude session imports with ArtifactData.
"""
import csv
import datetime
import json
import os

MAX_DOC_BYTES = 200_000
BATCH = 50

# Compact field lists keep each site document small. Anything not listed stays in the CSV only.
SITE_FIELDS = {
    "agents": ["reg_no", "name", "district", "category", "expires"],
    "projects": ["key", "project_id", "registration_no", "name", "builder", "location", "district", "valid_upto", "lapsed", "detail_url"],
    "documents": ["title", "url", "date", "type"],
}


def _flat(v):
    if isinstance(v, list):
        return " | ".join(str(x) for x in v)
    return "" if v is None else v


def write_csv(path, rows):
    keys = []
    for r in rows:
        keys += [k for k in r["data"] if k not in keys]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel and Numbers read Hindi/Punjabi text correctly
        w = csv.DictWriter(f, fieldnames=["first_seen", "last_seen"] + keys)
        w.writeheader()
        for r in rows:
            w.writerow(dict({k: _flat(v) for k, v in r["data"].items()}, first_seen=_day(r["first_seen"]), last_seen=_day(r["last_seen"])))


def _day(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""


def chunks(items, limit=MAX_DOC_BYTES):
    cur, size = [], 0
    for it in items:
        n = len(json.dumps(it, ensure_ascii=False).encode())
        if cur and size + n > limit:
            yield cur
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        yield cur


def run(cfg, store, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    docs_dir = os.path.join(out_dir, "site_docs")
    os.makedirs(docs_dir, exist_ok=True)
    for f in os.listdir(docs_dir):
        os.remove(os.path.join(docs_dir, f))
    report, ops, index = [], [], []
    today = datetime.date.today().isoformat()
    for sid, scfg in cfg["sources"].items():
        kinds = sorted({c["kind"] for c in store.counts() if c["source"] == sid})
        for kind in kinds:
            rows = store.records(sid, kind)
            csv_path = os.path.join(out_dir, "%s_%s.csv" % (sid, kind))
            write_csv(csv_path, rows)
            report.append("csv   %-40s %5d rows" % (os.path.relpath(csv_path, out_dir), len(rows)))
            if not scfg.get("publish"):
                continue
            districts = {d.lower() for d in scfg.get("export_districts", [])}
            fields = SITE_FIELDS.get(kind)
            items = [{k: r["data"].get(k) for k in fields} if fields else r["data"] for r in rows
                     if not districts or str(r["data"].get("district", "")).lower() in districts]
            for i, part in enumerate(chunks(items), 1):
                doc_id = "%s-%s-%d" % (sid, kind, i)
                body = {"source": sid, "kind": kind, "name": scfg.get("name", sid), "attribution": scfg.get("attribution", ""),
                        "updated": today, "part": i, "items": part}
                path = os.path.abspath(os.path.join(docs_dir, doc_id + ".json"))
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(body, f, ensure_ascii=False, separators=(",", ":"))
                ops.append({"op": "set", "collection": "ref", "doc_id": doc_id, "file_path": path})
                index.append({"id": doc_id, "source": sid, "kind": kind, "count": len(part)})
    held = [s for s, c in cfg["sources"].items() if c.get("enabled") and not c.get("publish")]
    if index:
        path = os.path.abspath(os.path.join(docs_dir, "index.json"))
        with open(path, "w") as f:
            json.dump({"updated": today, "parts": index}, f, separators=(",", ":"))
        ops.append({"op": "set", "collection": "ref", "doc_id": "index", "file_path": path})
    for f in os.listdir(out_dir):
        if f.startswith("site_batch_") and f.endswith(".json"):
            os.remove(os.path.join(out_dir, f))
    for i in range(0, len(ops), BATCH):
        path = os.path.join(out_dir, "site_batch_%d.json" % (i // BATCH + 1))
        with open(path, "w") as f:
            json.dump(ops[i:i + BATCH], f, indent=1)
        report.append("batch %-40s %5d writes" % (os.path.relpath(path, out_dir), len(ops[i:i + BATCH])))
    if held:
        report.append("not exported to the site (publish=false until the authority gives permission): " + ", ".join(held))
    return report
