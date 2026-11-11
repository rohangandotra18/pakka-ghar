#!/usr/bin/env python3
"""Tricity public-records fetcher. Runs on a Mac in India, where the state authority sites are reachable.

  python3 fetcher.py run                 fetch every enabled source that is due
  python3 fetcher.py run --source gmada  one source, even if not due
  python3 fetcher.py run --probe         also save each fetched page under data/probe/ for tuning
  python3 fetcher.py status              last run and record counts per source
  python3 fetcher.py changes --days 7    what appeared, changed or disappeared
  python3 fetcher.py export              CSVs for review, plus site import batches for publishable sources
"""
import argparse
import datetime
import fcntl
import importlib
import json
import logging
import logging.handlers
import os
import platform
import re
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sources.base import FetchError, Http  # noqa: E402
from store import Store  # noqa: E402

log = logging.getLogger("tricity")


def merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path=None):
    path = path or os.path.join(HERE, "config.json")
    with open(path) as f:
        cfg = json.load(f)
    local = os.path.join(os.path.dirname(path), "config.local.json")
    if os.path.exists(local):
        with open(local) as f:
            cfg = merge(cfg, json.load(f))
    if os.environ.get("TRICITY_CONTACT_EMAIL"):
        cfg["contact_email"] = os.environ["TRICITY_CONTACT_EMAIL"]
    cfg["data_dir"] = os.path.join(HERE, cfg.get("data_dir", "data")) if not os.path.isabs(cfg.get("data_dir", "data")) else cfg["data_dir"]
    return cfg


def setup_logging(data_dir, quiet=False):
    os.makedirs(os.path.join(data_dir, "logs"), exist_ok=True)
    log.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(os.path.join(data_dir, "logs", "fetcher.log"), maxBytes=2_000_000, backupCount=5)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    if not quiet:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(sh)


class Context:
    """What a source module gets: its own settings, the shared HTTP client and store, and a few helpers."""

    def __init__(self, source_id, scfg, gcfg, http, store, probe):
        mod = importlib.import_module("sources." + scfg["module"])
        self.module = mod
        self.source = source_id
        self.cfg = merge(getattr(mod, "DEFAULTS", {}), {k: v for k, v in scfg.items() if k not in ("module", "enabled", "publish")})
        self.global_cfg, self.http, self.store, self.probe = gcfg, http, store, probe
        self.data_dir = gcfg["data_dir"]

    def log(self, msg):
        log.info("[%s] %s", self.source, msg)

    def save_probe(self, name, html):
        if not self.probe:
            return
        folder = os.path.join(self.data_dir, "probe", self.source)
        os.makedirs(folder, exist_ok=True)
        slug = re.sub(r"[^\w]+", "_", name)[-100:].strip("_") or "page"
        with open(os.path.join(folder, slug + ".html"), "w", encoding="utf-8") as f:
            f.write(html)


def due(store, sid, scfg, gcfg):
    hours = float(scfg.get("every_hours", gcfg.get("every_hours", 6)))
    return time.time() - store.last_success(sid) >= hours * 3600 - 300


def notify(title, text):
    if platform.system() != "Darwin":
        return
    script = 'display notification %s with title %s' % (json.dumps(text[:200]), json.dumps(title))
    try:
        subprocess.run(["osascript", "-e", script], timeout=10, check=False, capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        pass


def cmd_run(cfg, args):
    lock = open(os.path.join(cfg["data_dir"], ".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("another run is in progress; exiting")
        return 0
    store = Store(os.path.join(cfg["data_dir"], "tricity.sqlite"))
    try:
        http = Http(cfg, store, lambda m: log.info(m))
    except FetchError as e:
        log.error(str(e))
        return 2
    wanted = args.source or [s for s, c in cfg["sources"].items() if c.get("enabled")]
    unknown = [s for s in wanted if s not in cfg["sources"]]
    if unknown:
        log.error("unknown source(s): %s. Known: %s", ", ".join(unknown), ", ".join(cfg["sources"]))
        return 2
    started, failures, totals = time.time(), [], [0, 0, 0]
    for sid in wanted:
        scfg = cfg["sources"][sid]
        if not args.source and not due(store, sid, scfg, cfg):
            log.info("[%s] not due yet", sid)
            continue
        if args.force or args.probe:
            for url in [scfg.get(k) for k in ("agents_url", "projects_url")] + list(scfg.get("pages", [])):
                if url:
                    store.forget_http_cache(url)
        run_id = store.start_run(sid)
        try:
            ctx = Context(sid, scfg, cfg, http, store, args.probe)
            a, c, r = ctx.module.run(ctx)
            store.finish_run(run_id, "ok", a, c, r)
            totals = [totals[0] + a, totals[1] + c, totals[2] + r]
        except Exception as e:  # one broken source must not stop the others
            store.finish_run(run_id, "error", message="%s\n%s" % (e, traceback.format_exc()))
            failures.append("%s: %s" % (sid, e))
            log.error("[%s] failed: %s", sid, e)
    store.db.commit()
    changes = store.recent_changes(started)
    write_digest(cfg, store)
    store.close()
    if changes:
        notify("Tricity fetcher", "%d new, %d changed, %d gone. Details: data/latest_changes.md" % tuple(totals))
    if failures:
        notify("Tricity fetcher: %d source(s) failed" % len(failures), "; ".join(failures))
    log.info("done: %d new, %d changed, %d gone, %d failed", totals[0], totals[1], totals[2], len(failures))
    return 1 if failures and len(failures) == len(wanted) else 0


def write_digest(cfg, store, days=7):
    rows = store.recent_changes(time.time() - days * 86400)
    lines = ["# Changes in the last %d days" % days, "", "Generated %s." % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), ""]
    if not rows:
        lines.append("No changes.")
    cur = None
    for r in reversed(rows):
        head = "%s / %s" % (r["source"], r["kind"])
        if head != cur:
            lines += ["", "## " + head, ""]
            cur = head
        lines.append("- %s **%s** %s" % (datetime.datetime.fromtimestamp(r["at"]).strftime("%d %b %H:%M"), r["change"], r["summary"] or r["key"]))
    with open(os.path.join(cfg["data_dir"], "latest_changes.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


def cmd_status(cfg, args):
    store = Store(os.path.join(cfg["data_dir"], "tricity.sqlite"))
    runs = {r["source"]: r for r in store.last_runs()}
    counts = store.counts()
    print("%-13s %-8s %-7s %-6s %-17s %s" % ("source", "enabled", "publish", "status", "last run", "records"))
    for sid, s in cfg["sources"].items():
        r = runs.get(sid)
        when = datetime.datetime.fromtimestamp(r["finished"] or r["started"]).strftime("%Y-%m-%d %H:%M") if r else "never"
        recs = ", ".join("%s %d" % (c["kind"], c["live"]) for c in counts if c["source"] == sid) or "-"
        print("%-13s %-8s %-7s %-6s %-17s %s" % (sid, "yes" if s.get("enabled") else "no", "yes" if s.get("publish") else "no",
                                                  r["status"] if r else "-", when, recs))
        if r and r["status"] == "error":
            print("    " + (r["message"] or "").splitlines()[0])
    store.close()
    return 0


def cmd_changes(cfg, args):
    store = Store(os.path.join(cfg["data_dir"], "tricity.sqlite"))
    for r in store.recent_changes(time.time() - args.days * 86400):
        print("%s  %-11s %-9s %-8s %s" % (datetime.datetime.fromtimestamp(r["at"]).strftime("%Y-%m-%d %H:%M"), r["source"], r["kind"], r["change"], r["summary"] or r["key"]))
    store.close()
    return 0


def cmd_export(cfg, args):
    import export
    store = Store(os.path.join(cfg["data_dir"], "tricity.sqlite"))
    try:
        for line in export.run(cfg, store, args.out or os.path.join(cfg["data_dir"], "export")):
            print(line)
    finally:
        store.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tricity public-records fetcher")
    ap.add_argument("--config", help="path to config.json")
    ap.add_argument("--quiet", action="store_true", help="log to file only (used by launchd)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--source", action="append", help="source id; repeat for several. Runs even if not due.")
    r.add_argument("--probe", action="store_true", help="save fetched pages to data/probe/ and skip downloads")
    r.add_argument("--force", action="store_true", help="ignore cached ETag/Last-Modified and refetch in full")
    sub.add_parser("status")
    c = sub.add_parser("changes")
    c.add_argument("--days", type=float, default=7)
    e = sub.add_parser("export")
    e.add_argument("--out")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    os.makedirs(cfg["data_dir"], exist_ok=True)
    setup_logging(cfg["data_dir"], args.quiet)
    return {"run": cmd_run, "status": cmd_status, "changes": cmd_changes, "export": cmd_export}[args.cmd](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
